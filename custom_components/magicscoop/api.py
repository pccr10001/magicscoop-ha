"""Protocol layer on top of MagicScoopMQTT (login, device list, control)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .const import (
    CMD_ALL_MS,
    CMD_CURRENT_STATUS,
    CMD_FORGOT_PASSWORD,
    CMD_GET_DIAGNOSE,
    CMD_GET_PASSWORD,
    CMD_GET_SETTINGS,
    CMD_LOGIN,
    CMD_PERFORM_ACTION,
    CMD_UPDATE_SETTINGS,
    DEVICE_TYPE_LITTER,
    topic_pub_cloud,
    topic_pub_device,
)
from .mqtt_client import MagicScoopMQTT

_LOGGER = logging.getLogger(__name__)


@dataclass
class MagicScoopDevice:
    """A device returned by CLOUD_ACCOUNT_ALL_MS."""

    dno: int
    name: str
    model: str
    version: str
    device_type: int

    @property
    def is_litter(self) -> bool:
        return self.device_type == DEVICE_TYPE_LITTER


class MagicScoopError(Exception):
    """Raised when the cloud returns a non-OK payload."""


class MagicScoopClient:
    """Wraps a MagicScoopMQTT with typed protocol operations."""

    def __init__(self, mqtt: MagicScoopMQTT):
        self.mqtt = mqtt

    # -- account ------------------------------------------------------
    async def async_send_verification(self, email: str, timeout: float = 15.0) -> None:
        """Trigger the verification-code email (CLOUD_FORGOT_PASSWORD)."""
        resp = await self.mqtt.async_request(
            topic_pub_cloud(), CMD_FORGOT_PASSWORD, {"UserName": email}, timeout=timeout
        )
        self._check(resp, CMD_FORGOT_PASSWORD)

    async def async_get_password(
        self, email: str, code: str, timeout: float = 15.0
    ) -> str:
        """Exchange the verification code for the encrypted password."""
        resp = await self.mqtt.async_request(
            topic_pub_cloud(),
            CMD_GET_PASSWORD,
            {"UserName": email, "VerificationCode": code},
            timeout=timeout,
        )
        self._check(resp, CMD_GET_PASSWORD)
        en_password = (resp.get("PAYLOAD") or {}).get("EnPassword")
        if not en_password:
            raise MagicScoopError("Cloud did not return a password")
        return en_password

    async def async_login(
        self, email: str, en_password: str, timeout: float = 15.0
    ) -> None:
        resp = await self.mqtt.async_request(
            topic_pub_cloud(),
            CMD_LOGIN,
            {"UserName": email, "EnPassword": en_password},
            timeout=timeout,
        )
        self._check(resp, CMD_LOGIN)

    async def async_get_devices(
        self, email: str, timeout: float = 15.0
    ) -> list[MagicScoopDevice]:
        """Fetch the account device list; the DATASET is double-encoded JSON."""
        resp = await self.mqtt.async_request(
            topic_pub_cloud(), CMD_ALL_MS, {"UserName": email}, timeout=timeout
        )
        self._check(resp, CMD_ALL_MS)
        payload = resp.get("PAYLOAD") or {}
        dataset = payload.get("DATASET")
        if not dataset:
            return []
        try:
            inner = json.loads(dataset)
        except json.JSONDecodeError:
            _LOGGER.warning("Unparseable DATASET from cloud")
            return []
        devices: list[MagicScoopDevice] = []
        for row in inner.get("DATAS", []):
            try:
                devices.append(
                    MagicScoopDevice(
                        dno=int(row["DNO"]),
                        name=str(row.get("SDEVICENAME", "")).strip() or str(row["DNO"]),
                        model=str(row.get("SCUSTOM", "")).strip(),
                        version=str(row.get("SVERSION", "")).strip(),
                        device_type=int(row.get("IDEVICETYPE", -1)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return devices

    # -- device -------------------------------------------------------
    async def async_get_status(self, dno: int) -> dict[str, Any]:
        resp = await self.mqtt.async_request(
            topic_pub_device(dno), CMD_CURRENT_STATUS, {"DNO": dno}
        )
        return resp.get("PAYLOAD") or {}

    async def async_get_settings(self, dno: int) -> dict[str, Any]:
        resp = await self.mqtt.async_request(
            topic_pub_device(dno), CMD_GET_SETTINGS, {"DNO": dno}
        )
        return resp.get("PAYLOAD") or {}

    async def async_get_diagnose(self, dno: int) -> dict[str, Any]:
        resp = await self.mqtt.async_request(
            topic_pub_device(dno), CMD_GET_DIAGNOSE, {"DNO": dno}
        )
        return resp.get("PAYLOAD") or {}

    async def async_perform(self, dno: int, command: int) -> None:
        """Send an MS_PERFORM_ACTION button command (e.g. 12 = start clean)."""
        resp = await self.mqtt.async_request(
            topic_pub_device(dno),
            CMD_PERFORM_ACTION,
            {"DNO": dno, "COMMAND": command},
        )
        self._check(resp, CMD_PERFORM_ACTION)

    async def async_update_settings(self, dno: int, **fields: Any) -> None:
        """Write one or more settings (MS_UPDATE_SETTINGS)."""
        payload: dict[str, Any] = {"DNO": dno}
        payload.update(fields)
        resp = await self.mqtt.async_request(
            topic_pub_device(dno), CMD_UPDATE_SETTINGS, payload
        )
        # The ack comes back with CMD == REMOTE_ACK, so _check by CMD would
        # fail; instead verify it is not an explicit error.
        message = (resp.get("PAYLOAD") or {}).get("Message", "OK")
        if message not in ("OK", "Success"):
            raise MagicScoopError(f"Update settings failed: {message}")

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _check(resp: dict[str, Any], expected_cmd: str) -> None:
        """Raise with the cloud's own message so callers can map it."""
        payload = resp.get("PAYLOAD") or {}
        message = payload.get("Message", "OK")
        if message in ("OK", "Success"):
            return
        _LOGGER.debug("%s rejected by cloud: %s", expected_cmd, message)
        raise MagicScoopError(str(message))


def generate_cid() -> str:
    """Generate a stable 12-digit client id (same shape as the app's CID)."""
    import random

    return str(random.randint(100_000_000_000, 999_999_999_999))
