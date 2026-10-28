"""Sensors: readable state from MS_CURRENT_STATUS / MS_GET_SETTINGS / MS_GET_DIAGNOSE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_STATUS, DEVICE_SUB_STATUS, LITTER_VOLUME, DOMAIN
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity


@dataclass(frozen=True)
class MagicScoopSensorDescription(SensorEntityDescription):
    """Sensor description with an accessor into the coordinator state."""

    # key inside status / settings / diagnose payload
    source: str = "status"
    field: str = ""
    value_fn: Callable[[Any], Any] | None = None


def _enum(mapping: dict[int, str]):
    def _fn(v: Any) -> str | None:
        if v is None:
            return None
        return mapping.get(int(v), "unknown")

    return _fn


SENSORS: list[MagicScoopSensorDescription] = [
    MagicScoopSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_STATUS.values()),
        source="status",
        field="DeviceStatus",
        value_fn=_enum(DEVICE_STATUS),
    ),
    MagicScoopSensorDescription(
        key="sub_status",
        translation_key="sub_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_SUB_STATUS.values()),
        source="status",
        field="DeviceSubStatus",
        value_fn=_enum(DEVICE_SUB_STATUS),
    ),
    MagicScoopSensorDescription(
        key="litter_volume",
        translation_key="litter_volume",
        device_class=SensorDeviceClass.ENUM,
        options=list(LITTER_VOLUME.values()),
        source="status",
        field="LitterVolume",
        value_fn=_enum(LITTER_VOLUME),
    ),
    MagicScoopSensorDescription(
        key="elapsed_time",
        translation_key="elapsed_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        source="status",
        field="ElapsedTime",
    ),
    MagicScoopSensorDescription(
        key="clean_times",
        translation_key="clean_times",
        state_class=SensorStateClass.TOTAL_INCREASING,
        source="settings",
        field="_CLEANTIMES",
    ),
    MagicScoopSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        source="settings",
        field="_VERSION",
    ),
    # --- diagnostics from MS_GET_DIAGNOSE ---
    MagicScoopSensorDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="diagnose",
        field="RSSI",
    ),
    MagicScoopSensorDescription(
        key="dc",
        translation_key="dc",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="diagnose",
        field="DC",
    ),
    MagicScoopSensorDescription(
        key="tof_position",
        translation_key="tof_position",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="diagnose",
        field="TOF_P",
    ),
    MagicScoopSensorDescription(
        key="rotate_angle",
        translation_key="rotate_angle",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="diagnose",
        field="ROTATE_A",
    ),
    MagicScoopSensorDescription(
        key="rotate_speed",
        translation_key="rotate_speed",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="diagnose",
        field="ROTATE_S",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopSensor(coordinator, dno, desc)
        for dno in coordinator.devices
        for desc in SENSORS
    )


class MagicScoopSensor(MagicScoopEntity, SensorEntity):
    """A single readable value from a litter box."""

    entity_description: MagicScoopSensorDescription

    def __init__(
        self,
        coordinator: MagicScoopCoordinator,
        dno: int,
        description: MagicScoopSensorDescription,
    ) -> None:
        super().__init__(coordinator, dno)
        self.entity_description = description
        self._attr_unique_id = f"{dno}_{description.key}"

    @property
    def native_value(self) -> Any:
        # coordinator.status/settings/diagnose are keyed by DNO first.
        store = getattr(self.coordinator, self.entity_description.source, None) or {}
        payload = store.get(self._dno) or {}
        raw = payload.get(self.entity_description.field)
        if raw is None:
            return None
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(raw)
        return raw
