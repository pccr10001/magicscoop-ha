"""Binary sensors derived from MS_CURRENT_STATUS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity

# DeviceStatus numeric values (see const.DEVICE_STATUS)
STATUS_OCCUPIED = 5
STATUS_CLUMPING = 6
STATUS_WASTE_FULL = 15
CLEAN_STATUSES = {7, 8, 9, 10}  # auto / manual / periodic / remote clean


@dataclass(frozen=True)
class MagicScoopBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool] | None = None


def _cat_present(payload: dict[str, Any]) -> bool:
    return payload.get("DeviceStatus") in (STATUS_OCCUPIED, STATUS_CLUMPING)


def _waste_full(payload: dict[str, Any]) -> bool:
    return payload.get("DeviceStatus") == STATUS_WASTE_FULL


def _cleaning(payload: dict[str, Any]) -> bool:
    return payload.get("DeviceStatus") in CLEAN_STATUSES


BINARY_SENSORS: list[MagicScoopBinaryDescription] = [
    MagicScoopBinaryDescription(
        key="cat_present",
        translation_key="cat_present",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        value_fn=_cat_present,
    ),
    MagicScoopBinaryDescription(
        key="waste_full",
        translation_key="waste_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_waste_full,
    ),
    MagicScoopBinaryDescription(
        key="cleaning",
        translation_key="cleaning",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_cleaning,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopBinarySensor(coordinator, dno, desc)
        for dno in coordinator.devices
        for desc in BINARY_SENSORS
    )


class MagicScoopBinarySensor(MagicScoopEntity, BinarySensorEntity):
    entity_description: MagicScoopBinaryDescription

    def __init__(
        self,
        coordinator: MagicScoopCoordinator,
        dno: int,
        description: MagicScoopBinaryDescription,
    ) -> None:
        super().__init__(coordinator, dno)
        self.entity_description = description
        self._attr_unique_id = f"{dno}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        payload = self.coordinator.status.get(self._dno)
        if not payload or not self.entity_description.value_fn:
            return None
        return self.entity_description.value_fn(payload)
