"""DataUpdateCoordinator: one MQTT connection per account + device state."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MagicScoopClient, MagicScoopDevice, MagicScoopError
from .const import (
    CONF_DEVICES,
    CONF_EMAIL,
    CONF_EN_PASSWORD,
    DOMAIN,
    topic_sub_device,
)
from .mqtt_client import MagicScoopMQTT, MagicScoopTimeout

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
DIAGNOSE_INTERVAL = 6  # refresh diagnose every Nth poll (~2 min)


class MagicScoopCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Coordinator for a single MagicScoop account."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.email: str = entry.data[CONF_EMAIL]
        self.en_password: str = entry.data[CONF_EN_PASSWORD]
        self.devices: dict[int, MagicScoopDevice] = {}
        self.status: dict[int, dict[str, Any]] = {}
        self.settings: dict[int, dict[str, Any]] = {}
        self.diagnose: dict[int, dict[str, Any]] = {}
        self._mqtt: MagicScoopMQTT | None = None
        self._client: MagicScoopClient | None = None
        self._poll_count = 0

    @property
    def client(self) -> MagicScoopClient:
        assert self._client is not None
        return self._client

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def async_init(self) -> None:
        """Connect, login, subscribe and seed state before first refresh."""
        from .api import generate_cid

        self._mqtt = MagicScoopMQTT(self.hass, entry_cid(self.entry) or generate_cid())
        self._mqtt.message_callback = self._handle_message
        self._mqtt.connected_callback = self._handle_reconnect
        await self._mqtt.async_start()
        self._client = MagicScoopClient(self._mqtt)

        await self._client.async_login(self.email, self.en_password)

        # Seed the device list from the entry (kept so entities survive a
        # transient cloud failure), then try to refresh it.
        await self._async_load_devices()

        # The cloud reply topic is subscribed automatically on (re)connect.
        for dno in self.devices:
            self._mqtt.subscribe(topic_sub_device(dno))

        # Initial full fetch.
        await self._async_fetch_all()

    async def async_shutdown(self) -> None:
        if self._mqtt is not None:
            await self._mqtt.async_stop()
            self._mqtt = None

    async def _handle_reconnect(self) -> None:
        """Re-login + re-subscribe after a broker-level reconnect."""
        try:
            await self._client.async_login(self.email, self.en_password)
            for dno in self.devices:
                self._mqtt.subscribe(topic_sub_device(dno))
            await self._async_fetch_all()
        except (MagicScoopError, MagicScoopTimeout) as err:
            _LOGGER.warning("MagicScoop re-login failed: %s", err)

    async def _async_load_devices(self) -> None:
        """Refresh device list from the cloud, falling back to the stored one."""
        stored = {
            int(d["dno"]): MagicScoopDevice(
                dno=int(d["dno"]),
                name=d.get("name", str(d["dno"])),
                model=d.get("model", ""),
                version=d.get("version", ""),
                device_type=d.get("device_type", 0),
            )
            for d in self.entry.data.get(CONF_DEVICES, [])
        }
        try:
            fresh = await self._client.async_get_devices(self.email)
            litter = {d.dno: d for d in fresh if d.is_litter}
            if litter:
                self.devices = litter
                return
            _LOGGER.warning("Cloud returned no litter devices; using stored list")
        except (MagicScoopError, MagicScoopTimeout) as err:
            _LOGGER.warning("Could not refresh device list: %s", err)
        self.devices = stored

    # ------------------------------------------------------------------
    # message handling (device pushes + cloud responses)
    # ------------------------------------------------------------------
    @callback
    def _handle_message(self, data: dict[str, Any]) -> None:
        payload = data.get("PAYLOAD") or {}
        dno = payload.get("DNO")
        if dno is None:
            return
        dno = int(dno)
        cmd = data.get("CMD", "")
        if cmd == "MS_CURRENT_STATUS":
            self.status[dno] = payload
        elif cmd == "MS_GET_SETTINGS":
            self.settings[dno] = payload.get("SETTINGS", {})
            # keep the non-SETTINGS meta fields alongside
            self.settings[dno]["_VERSION"] = payload.get("VERSION", "")
            self.settings[dno]["_MODAL"] = payload.get("MODAL", "")
            self.settings[dno]["_CLEANTIMES"] = payload.get("CleanTimes")
        elif cmd == "MS_GET_DIAGNOSE":
            self.diagnose[dno] = payload
        else:
            return
        # _handle_message is already scheduled onto the event loop by the
        # MQTT client, so it is safe to notify listeners directly.
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # polling
    # ------------------------------------------------------------------
    async def _async_fetch_all(self) -> None:
        for dno in self.devices:
            try:
                self.status[dno] = await self._client.async_get_status(dno)
            except (MagicScoopError, MagicScoopTimeout) as err:
                _LOGGER.debug("status fetch %s: %s", dno, err)
            try:
                payload = await self._client.async_get_settings(dno)
                settings = payload.get("SETTINGS", {})
                settings["_VERSION"] = payload.get("VERSION", "")
                settings["_MODAL"] = payload.get("MODAL", "")
                settings["_CLEANTIMES"] = payload.get("CleanTimes")
                self.settings[dno] = settings
            except (MagicScoopError, MagicScoopTimeout) as err:
                _LOGGER.debug("settings fetch %s: %s", dno, err)
            try:
                self.diagnose[dno] = await self._client.async_get_diagnose(dno)
            except (MagicScoopError, MagicScoopTimeout) as err:
                _LOGGER.debug("diagnose fetch %s: %s", dno, err)

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        if self._client is None:
            raise UpdateFailed("Not connected")
        self._poll_count += 1
        try:
            for dno in self.devices:
                self.status[dno] = await self._client.async_get_status(dno)
            if self._poll_count % DIAGNOSE_INTERVAL == 0:
                for dno in self.devices:
                    self.diagnose[dno] = await self._client.async_get_diagnose(dno)
        except (MagicScoopError, MagicScoopTimeout) as err:
            raise UpdateFailed(str(err)) from err
        return self.status

    # ------------------------------------------------------------------
    # operations used by entities
    # ------------------------------------------------------------------
    async def async_perform(self, dno: int, command: int) -> None:
        await self.client.async_perform(dno, command)
        # nudge a status refresh so the UI reflects the new state quickly
        try:
            self.status[dno] = await self.client.async_get_status(dno)
        except (MagicScoopError, MagicScoopTimeout):
            pass
        self.async_update_listeners()

    async def async_update_settings(self, dno: int, **fields: Any) -> None:
        await self.client.async_update_settings(dno, **fields)
        try:
            payload = await self.client.async_get_settings(dno)
            settings = payload.get("SETTINGS", {})
            settings["_VERSION"] = payload.get("VERSION", "")
            settings["_MODAL"] = payload.get("MODAL", "")
            settings["_CLEANTIMES"] = payload.get("CleanTimes")
            self.settings[dno] = settings
        except (MagicScoopError, MagicScoopTimeout):
            pass
        self.async_update_listeners()


def entry_cid(entry: ConfigEntry) -> str | None:
    return entry.data.get("cid")
