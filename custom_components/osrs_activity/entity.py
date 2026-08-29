"""Shared base for every entity this integration creates."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import ActivityCoordinator


class OsrsActivityEntity(Entity):
    """One player's device, and a subscription to its snapshots."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: ActivityCoordinator, key: str) -> None:
        self.coordinator = coordinator
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=f"OSRS Activity ({coordinator.username})",
            manufacturer="Old School RuneScape",
            model="Activity tracker",
            entry_type=None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self.coordinator.entry_id}",
                self.async_write_ha_state,
            )
        )

    @property
    def data(self) -> dict:
        return self.coordinator.data
