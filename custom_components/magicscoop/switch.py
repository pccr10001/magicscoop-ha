"""Switches: boolean settings written via MS_UPDATE_SETTINGS."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SWITCH_FIELDS
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopSwitch(coordinator, dno, field)
        for dno in coordinator.devices
        for field in SWITCH_FIELDS
    )


class MagicScoopSwitch(MagicScoopEntity, SwitchEntity):
    """One boolean setting (e.g. CleanUVEnable)."""

    def __init__(
        self, coordinator: MagicScoopCoordinator, dno: int, field: str
    ) -> None:
        super().__init__(coordinator, dno)
        self._field = field
        self._attr_unique_id = f"{dno}_{field}"
        self._attr_translation_key = field

    @property
    def is_on(self) -> bool | None:
        settings = self.coordinator.settings.get(self._dno) or {}
        raw = settings.get(self._field)
        if raw is None:
            return None
        return bool(raw)

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_update_settings(self._dno, **{self._field: True})

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_update_settings(self._dno, **{self._field: False})
