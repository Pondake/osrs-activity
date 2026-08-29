"""Idle, as the RuneLite plugin sees it."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities([IdleBinarySensor(coordinator), OnlineBinarySensor(coordinator)])


class IdleBinarySensor(OsrsActivityEntity, BinarySensorEntity):
    """On when the player is standing around doing nothing.

    Turned on by the plugin's idle event and turned off by the next XP gain.
    How long you have to stand still first is the Idle delay in the RuneLite
    plugin's own panel; this integration keeps no threshold of its own, so
    there is only one place to change it.

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


class OnlineBinarySensor(OsrsActivityEntity, BinarySensorEntity):
    """On while the RuneLite plugin is still pushing for this player.

    Read from last_ping_time on the RuneLite status sensor rather than from
    that sensor's state. The state also depends on a usable world number, and a
    build in August 2026 stopped sending one, which left it reading False for a
    player who was online. A ping only moves when the plugin actually sends
    something, so it does not have that dependency.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "online")

    @property
    def is_on(self) -> bool:
        return bool(self.data.get("online", False))

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_ping": self.data.get("last_ping")}
