"""Numbers: numeric settings written via MS_UPDATE_SETTINGS.

MoveSensitivity / RotateSensitivity are deliberately not exposed: the mobile
app has no UI for them (see const.NUMBER_FIELDS).
"""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NUMBER_FIELDS
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity

# field -> (device_class, unit)
_FIELD_META: dict[str, tuple] = {
    "PeriodicActionHour": (NumberDeviceClass.DURATION, UnitOfTime.HOURS),
    "PeriodicActionMin": (NumberDeviceClass.DURATION, UnitOfTime.MINUTES),
    "PeriodicActionStopHour": (NumberDeviceClass.DURATION, UnitOfTime.HOURS),
    "PeriodicActionStopMin": (NumberDeviceClass.DURATION, UnitOfTime.MINUTES),
    "SleepStartHour": (NumberDeviceClass.DURATION, UnitOfTime.HOURS),
    "SleepStartMin": (NumberDeviceClass.DURATION, UnitOfTime.MINUTES),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopNumber(coordinator, dno, field)
        for dno in coordinator.devices
        for field in NUMBER_FIELDS
    )


class MagicScoopNumber(MagicScoopEntity, NumberEntity):
    """One numeric setting (e.g. SleepStartHour)."""

    _attr_mode = NumberMode.AUTO

    def __init__(
        self, coordinator: MagicScoopCoordinator, dno: int, field: str
    ) -> None:
        super().__init__(coordinator, dno)
        self._field = field
        self._attr_unique_id = f"{dno}_{field}"
        self._attr_translation_key = field
        lo, hi = NUMBER_FIELDS[field]
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = 1
        device_class, unit = _FIELD_META.get(field, (None, None))
        if device_class is not None:
            self._attr_device_class = device_class
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> int | None:
        settings = self.coordinator.settings.get(self._dno) or {}
        raw = settings.get(self._field)
        if raw is None:
            return None
        return int(raw)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_settings(
            self._dno, **{self._field: int(value)}
        )
