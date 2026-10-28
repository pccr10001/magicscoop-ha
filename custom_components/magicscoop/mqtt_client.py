"""Async MQTT client for MagicScoop (paho-mqtt, mTLS, TID request/response).

All blocking work (SSL context creation, DNS, connect) is kept off the event
loop: the SSLContext is built in the executor and handed to paho via
``tls_set_context``, and the connection is opened with ``connect_async``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant

from . import certs
from .const import (
    BROKER_HOST,
    BROKER_PORT,
    BROKER_USER,
    BROKER_PASS,
    KEEPALIVE,
    topic_sub_cloud,
)

_LOGGER = logging.getLogger(__name__)


class MagicScoopTimeout(Exception):
    """Raised when a request has no matching response in time."""


class MagicScoopConnectError(MagicScoopTimeout):
    """Raised when the broker refuses the connection (CONNACK rc != 0)."""


def _build_ssl_context() -> ssl.SSLContext:
    """Load the bundled CA + client certificate (blocking, run in executor)."""
    ca_path, cert_path, key_path = certs.materialize()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(ca_path)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx


def _make_client(cid: str) -> mqtt.Client:
    """Create a paho client compatible with both paho 1.x and 2.x."""
    kwargs = dict(client_id=cid, protocol=mqtt.MQTTv311)
    if hasattr(mqtt, "CallbackAPIVersion"):  # paho 2.x
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1, **kwargs
        )
    return mqtt.Client(**kwargs)  # paho 1.x


class MagicScoopMQTT:
    """One MQTT connection bound to a single account CID.

    - mTLS to the broker (client cert bundled from the app).
    - Shared app-level credentials, identical for every install.
    - Correlates request/response by the numeric ``TID`` field, like the app.
    """

    def __init__(self, hass: HomeAssistant, cid: str):
        self.hass = hass
        self.cid = str(cid)
        self._client = _make_client(self.cid)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.username_pw_set(BROKER_USER, BROKER_PASS)
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)

        self._pending: dict[int, asyncio.Future] = {}
        # Always listen on our own reply topic, so responses are never missed
        # (config flow and coordinator both rely on this).
        self._topics: set[str] = {topic_sub_cloud(self.cid)}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = asyncio.Event()
        self._ever_connected = False
        # Resolved with the first CONNACK return code, so async_start() can
        # fail fast instead of waiting for the full timeout.
        self._connect_result: asyncio.Future | None = None

        # Called in the event loop for every parsed message.
        self.message_callback: Callable[[dict[str, Any]], None] | None = None
        # Called in the event loop on every reconnect after the first connect.
        self.connected_callback: Callable[[], Any] | None = None

    # ------------------------------------------------------------------
    # connection lifecycle
    # ------------------------------------------------------------------
    async def async_start(self) -> None:
        self._loop = asyncio.get_running_loop()

        # Building the SSLContext reads cert files -> blocking, so do it in
        # the executor and hand the finished context to paho.
        context = await self.hass.async_add_executor_job(_build_ssl_context)
        self._client.tls_set_context(context)
        self._client.tls_insecure_set(False)

        # connect_async does the DNS lookup + TCP connect in paho's own
        # thread, so nothing blocks here.
        self._connect_result = self._loop.create_future()
        self._client.connect_async(BROKER_HOST, BROKER_PORT, KEEPALIVE)
        self._client.loop_start()
        try:
            rc = await asyncio.wait_for(self._connect_result, timeout=30)
        except asyncio.TimeoutError as err:
            await self.async_stop()
            raise MagicScoopTimeout("Timed out connecting to MQTT broker") from err
        if rc != 0:
            await self.async_stop()
            raise MagicScoopConnectError(
                f"MQTT broker refused the connection (CONNACK rc={rc})"
            )

    async def async_stop(self) -> None:
        try:
            self._client.disconnect()
            # Give paho a moment to flush the DISCONNECT packet before
            # tearing the network loop down, so the broker releases the
            # client id cleanly.
            await asyncio.sleep(0.2)
        finally:
            self._client.loop_stop()

    def subscribe(self, topic: str) -> None:
        """Subscribe now and re-subscribe automatically after a reconnect."""
        is_new = topic not in self._topics
        self._topics.add(topic)
        if is_new and self._connected.is_set():
            self._client.subscribe(topic, qos=1)

    # ------------------------------------------------------------------
    # paho callbacks (run in paho's network thread)
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            # 0 ok, 1 bad proto, 2 id rejected, 3 server unavailable,
            # 4 bad username/password, 5 not authorized
            _LOGGER.error(
                "MagicScoop MQTT connect refused rc=%s (cid=%s)", rc, self.cid
            )
            if self._loop:
                self._loop.call_soon_threadsafe(self._resolve_connect, rc)
            return
        _LOGGER.debug("MagicScoop MQTT connected (cid=%s)", self.cid)
        for topic in list(self._topics):
            client.subscribe(topic, qos=1)
        if self._loop:
            self._loop.call_soon_threadsafe(self._resolve_connect, rc)

    def _resolve_connect(self, rc: int) -> None:
        """Runs on the event loop; publishes the CONNACK result exactly once."""
        if self._connect_result is not None and not self._connect_result.done():
            self._connect_result.set_result(rc)
        if rc != 0:
            return
        self._connected.set()
        # Fire the reconnect hook only after the first successful connect, so
        # the caller's own post-connect setup isn't duplicated/raced.
        if self.connected_callback and self._ever_connected:
            self._fire_connected()
        self._ever_connected = True

    def _fire_connected(self):
        assert self._loop is not None
        result = self.connected_callback()
        if asyncio.iscoroutine(result):
            self._loop.create_task(result)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        _LOGGER.debug("MagicScoop MQTT disconnected rc=%s", rc)
        if self._loop:
            self._loop.call_soon_threadsafe(self._connected.clear)

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001 - ignore non-JSON payloads
            return
        if not isinstance(data, dict) or self._loop is None:
            return
        tid = data.get("TID")
        if tid is not None:
            fut = self._pending.get(tid)
            if fut is not None and not fut.done():
                self._loop.call_soon_threadsafe(fut.set_result, data)
        if self.message_callback is not None:
            self._loop.call_soon_threadsafe(self.message_callback, data)

    # ------------------------------------------------------------------
    # request / response
    # ------------------------------------------------------------------
    async def async_request(
        self,
        topic: str,
        cmd: str,
        payload: dict[str, Any],
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Publish a command and await the response echoing the same TID."""
        assert self._loop is not None, "async_start() must be awaited first"
        tid = random.randint(10**11, 10**12 - 1)
        fut: asyncio.Future = self._loop.create_future()
        self._pending[tid] = fut
        body = {"CMD": cmd, "CID": self.cid, "TID": tid, "PAYLOAD": payload}
        self._client.publish(topic, json.dumps(body))
        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as err:
            _LOGGER.debug("MagicScoop %s: no reply within %ss", cmd, timeout)
            raise MagicScoopTimeout(f"{cmd} timed out after {timeout}s") from err
        finally:
            self._pending.pop(tid, None)
        # Deferred formatting: only rendered when debug logging is enabled.
        _LOGGER.debug("MagicScoop %s <- %s", cmd, resp)
        return resp