"""Selects: enum settings written via MS_UPDATE_SETTINGS."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SELECT_SPECS
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopSelect(coordinator, dno, field)
        for dno in coordinator.devices
        for field in SELECT_SPECS
    )


class MagicScoopSelect(MagicScoopEntity, SelectEntity):
    """One enum setting (e.g. CleanMode = auto/manual/periodic)."""

    def __init__(
        self, coordinator: MagicScoopCoordinator, dno: int, field: str
    ) -> None:
        super().__init__(coordinator, dno)
        self._field = field
        self._spec = SELECT_SPECS[field]
        self._attr_unique_id = f"{dno}_{field}"
        self._attr_translation_key = field
        self._attr_options = list(self._spec["options"])

    @property
    def current_option(self) -> str | None:
        settings = self.coordinator.settings.get(self._dno) or {}
        raw = settings.get(self._field)
        if raw is None:
            return None
        return self._spec["v2k"].get(int(raw))

    async def async_select_option(self, option: str) -> None:
        value = self._spec["k2v"][option]
        await self.coordinator.async_update_settings(self._dno, **{self._field: value})
