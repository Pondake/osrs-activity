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

    Turned on and off by the plugin's two idle events. How long you have to
    stand still first is the Idle delay in the RuneLite plugin's own panel;
    this integration keeps no threshold of its own, so there is only one place
    to change it.

    Turning off used to wait for the next XP gain, which meant this stayed on
    through banking, walking and dialogue -- none of which grant XP. The plugin
    now reports that edge itself. The XP fallback is still there underneath for
    a client that does not send it.
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
            # The plugin's own count of the current spell, which starts at the
            # tick the player stopped rather than at the Idle delay later.
            "ticks": self.data.get("idle_ticks", 0),
            # How long the spell that just ended lasted. Readable at the moment
            # this turns off, which is the moment worth automating on: back
            # from a pause, or back after ten minutes away.
            "last_seconds": self.data.get("last_idle_seconds", 0),
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
