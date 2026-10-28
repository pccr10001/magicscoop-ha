"""Config flow: email -> verification code -> pick litter boxes.

The whole flow shares a single MQTT connection (like the app does), which keeps
the same client id and subscription across the email/code/device steps. This
avoids reconnects and guarantees the reply topic is being listened to.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import MagicScoopClient, MagicScoopError, generate_cid
from .crypto import encrypt_verification_code
from .const import (
    CONF_CID,
    CONF_DEVICES,
    CONF_EMAIL,
    CONF_EN_PASSWORD,
    DOMAIN,
)
from .mqtt_client import MagicScoopMQTT, MagicScoopTimeout

_LOGGER = logging.getLogger(__name__)

# Account-level calls can be slow; give them more room than a device call.
ACCOUNT_TIMEOUT = 25.0


def _map_cloud_error(err: Exception) -> tuple[str, str]:
    """Return (translation_key, raw_message) for a cloud rejection."""
    raw = str(err)
    low = raw.lower()
    if "does not exist" in low or "not found" in low or "no account" in low:
        return "account_not_found", raw
    if "verification" in low or "verify" in low or "expired" in low:
        return "invalid_code", raw
    return "cloud_error", raw


def _email_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_EMAIL,
                default=(defaults or {}).get(CONF_EMAIL, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
        }
    )


def _code_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("code"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
        }
    )


class MagicScoopConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a MagicScoop config flow (one flow per account)."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._cid: str = ""
        self._en_password: str = ""
        self._devices: list[dict[str, Any]] = []
        self._mqtt: MagicScoopMQTT | None = None
        self._client: MagicScoopClient | None = None

    # ------------------------------------------------------------------
    # shared connection
    # ------------------------------------------------------------------
    async def _async_ensure_connection(self) -> MagicScoopClient:
        """Open the MQTT connection once and reuse it for every step."""
        if self._client is not None:
            return self._client
        if not self._cid:
            self._cid = generate_cid()
        _LOGGER.debug("MagicScoop flow: connecting with cid=%s", self._cid)
        mqtt = MagicScoopMQTT(self.hass, self._cid)
        await mqtt.async_start()
        self._mqtt = mqtt
        self._client = MagicScoopClient(mqtt)
        return self._client

    async def _async_close_connection(self) -> None:
        if self._mqtt is not None:
            try:
                await self._mqtt.async_stop()
            except Exception:  # noqa: BLE001 - never fail the flow on cleanup
                _LOGGER.debug("Error while closing MQTT", exc_info=True)
            self._mqtt = None
            self._client = None

    @callback
    def async_remove(self) -> None:
        """Called (synchronously) when the flow is discarded.

        HA's base implementation is a plain method, so we schedule the async
        cleanup instead of making this a coroutine.
        """
        if self._mqtt is None:
            return
        try:
            self.hass.async_create_task(self._async_close_connection())
        except Exception:  # noqa: BLE001 - never fail flow teardown
            _LOGGER.debug("Could not schedule MQTT cleanup", exc_info=True)

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the account email, then fire off the verification code."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            self._email = email
            try:
                client = await self._async_ensure_connection()
                await client.async_send_verification(email, timeout=ACCOUNT_TIMEOUT)
            except MagicScoopTimeout:
                await self._async_close_connection()
                errors["base"] = "cannot_connect"
            except MagicScoopError as err:
                key, raw = _map_cloud_error(err)
                errors["base"] = key
                placeholders["message"] = raw
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error sending verification code")
                errors["base"] = "unknown"
            else:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=_email_schema(user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the verification code, then fetch devices."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            code = user_input["code"].strip()
            try:
                # The app never sends the code in the clear: it is
                # 3DES-encrypted and base64-encoded before transmission.
                encrypted_code = encrypt_verification_code(code)
            except ValueError:
                errors["base"] = "code_format"
            else:
                try:
                    client = await self._async_ensure_connection()
                    self._en_password = await client.async_get_password(
                        self._email, encrypted_code, timeout=ACCOUNT_TIMEOUT
                    )
                    await client.async_login(
                        self._email, self._en_password, timeout=ACCOUNT_TIMEOUT
                    )
                    devices = await client.async_get_devices(
                        self._email, timeout=ACCOUNT_TIMEOUT
                    )
                    self._devices = [
                        {
                            "dno": d.dno,
                            "name": d.name,
                            "model": d.model,
                            "version": d.version,
                            "device_type": d.device_type,
                        }
                        for d in devices
                        if d.is_litter
                    ]
                except MagicScoopTimeout as err:
                    _LOGGER.debug("MagicScoop flow timeout: %s", err)
                    errors["base"] = "cannot_connect"
                except MagicScoopError as err:
                    _LOGGER.debug("MagicScoop flow cloud error: %s", err)
                    key, raw = _map_cloud_error(err)
                    errors["base"] = key
                    placeholders["message"] = raw
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error verifying code")
                    errors["base"] = "unknown"
                else:
                    if not self._devices:
                        errors["base"] = "no_devices"
                    else:
                        return await self.async_step_devices()

        return self.async_show_form(
            step_id="code",
            data_schema=_code_schema(),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Multi-select which litter boxes to add."""
        errors: dict[str, str] = {}
        options = {str(d["dno"]): f"{d['name']} ({d['dno']})" for d in self._devices}
        if user_input is not None:
            selected = user_input.get(CONF_DEVICES) or []
            picked = [d for d in self._devices if str(d["dno"]) in selected]
            if not picked:
                errors["base"] = "no_devices"
            else:
                await self._async_close_connection()
                return self.async_create_entry(
                    title=self._email,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_EN_PASSWORD: self._en_password,
                        CONF_CID: self._cid,
                        CONF_DEVICES: picked,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICES, default=list(options.keys())): (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in options.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="devices", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return MagicScoopOptionsFlow(config_entry)


class MagicScoopOptionsFlow(config_entries.OptionsFlow):
    """Options flow: re-pick devices for an existing account.

    Newer Home Assistant injects ``config_entry`` automatically; older versions
    pass it to the constructor. Support both.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        self._fallback_entry = config_entry

    def _resolve_entry(self) -> config_entries.ConfigEntry:
        entry = getattr(self, "config_entry", None)
        if entry is not None:
            return entry
        assert self._fallback_entry is not None
        return self._fallback_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        target = self._resolve_entry()
        stored = target.data.get(CONF_DEVICES, [])
        all_options = {str(d["dno"]): f"{d['name']} ({d['dno']})" for d in stored}
        current = [str(d["dno"]) for d in stored]

        if user_input is not None:
            selected = user_input.get(CONF_DEVICES) or []
            new_devices = [d for d in stored if str(d["dno"]) in selected]
            if not new_devices:
                errors["base"] = "no_devices"
            else:
                new_data = {**target.data, CONF_DEVICES: new_devices}
                self.hass.config_entries.async_update_entry(target, data=new_data)
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICES, default=current): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=k, label=v)
                            for k, v in all_options.items()
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
