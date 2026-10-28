"""Buttons: MS_PERFORM_ACTION commands (start clean / reset / sterilize / pause)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PERFORM_PAUSE,
    PERFORM_RESET,
    PERFORM_START_CLEAN,
    PERFORM_STERILIZE,
)
from .coordinator import MagicScoopCoordinator
from .entity import MagicScoopEntity


@dataclass(frozen=True)
class MagicScoopButtonDescription(ButtonEntityDescription):
    command: int = 0


BUTTONS: list[MagicScoopButtonDescription] = [
    MagicScoopButtonDescription(
        key="start_clean",
        translation_key="start_clean",
        command=PERFORM_START_CLEAN,
    ),
    MagicScoopButtonDescription(
        key="pause",
        translation_key="pause",
        command=PERFORM_PAUSE,
    ),
    MagicScoopButtonDescription(
        key="reset",
        translation_key="reset",
        command=PERFORM_RESET,
    ),
    MagicScoopButtonDescription(
        key="sterilize",
        translation_key="sterilize",
        command=PERFORM_STERILIZE,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MagicScoopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MagicScoopButton(coordinator, dno, desc)
        for dno in coordinator.devices
        for desc in BUTTONS
    )


class MagicScoopButton(MagicScoopEntity, ButtonEntity):
    entity_description: MagicScoopButtonDescription

    def __init__(
        self,
        coordinator: MagicScoopCoordinator,
        dno: int,
        description: MagicScoopButtonDescription,
    ) -> None:
        super().__init__(coordinator, dno)
        self.entity_description = description
        self._attr_unique_id = f"{dno}_{description.key}"

    async def async_press(self) -> None:
        await self.coordinator.async_perform(
            self._dno, self.entity_description.command
        )
