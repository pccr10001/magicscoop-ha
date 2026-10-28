"""Base entity for MagicScoop."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MagicScoopCoordinator


class MagicScoopEntity(CoordinatorEntity[MagicScoopCoordinator]):
    """Base class: one physical litter box, keyed by its DNO."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MagicScoopCoordinator, dno: int) -> None:
        super().__init__(coordinator)
        self._dno = dno
        device = coordinator.devices.get(dno)
        name = device.name if device else str(dno)
        model = (device.model if device else "") or "MagicScoop"
        version = device.version if device else ""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(dno))},
            name=name,
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=version,
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._dno in self.coordinator.devices
            and self._dno in self.coordinator.status
        )
