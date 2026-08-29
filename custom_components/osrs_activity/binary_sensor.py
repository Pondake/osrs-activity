"""Idle, as the RuneLite plugin sees it."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ActivityCoordinator
from .entity import OsrsActivityEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ActivityCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IdleBinarySensor(coordinator)])


class IdleBinarySensor(OsrsActivityEntity, BinarySensorEntity):
    """On when the player is standing around doing nothing.

    Turned on by the plugin's idle event and turned off by the next XP gain.
    How long you have to stand still first is the Idle delay in the RuneLite
    plugin's own panel -- this integration deliberately keeps no threshold of
    its own, because two thresholds is two answers to the same question.

    That also means the "not idle any more" edge is only as fast as your next
    XP drop, which on a slow skill can be a while.
    """

    _attr_icon = "mdi:sleep"

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "idle")

    @property
    def is_on(self) -> bool:
        return bool(self.data.get("idle", False))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "since": self.data.get("idle_since"),
            "seconds": self.data.get("idle_seconds", 0),
        }
