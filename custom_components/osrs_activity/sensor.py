"""Sensors.

One of these carries the whole picture in its attributes and the rest are
conveniences. That split is deliberate: a template that draws a screen wants
every row in one place, and an automation that only cares whether you switched
to ranged should not have to dig through a list to find out.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import DOMAIN
from .coordinator import ActivityCoordinator
from .entity import OsrsActivityEntity

# Kept out of the published attributes. It is bookkeeping, it is the largest
# thing in the snapshot, and nothing outside this integration can use it.
INTERNAL = ("sessions_raw",)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ActivityCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            XpSessionSensor(coordinator),
            FocusSkillSensor(coordinator),
            SessionXpSensor(coordinator),
            XpPerHourSensor(coordinator),
            CombatStyleSensor(coordinator),
        ]
    )


@dataclass
class StoredSessions(ExtraStoredData):
    """The live counters, so a reload does not wipe your sitting.

    This is stored beside the state rather than inside the attributes: it is
    bookkeeping, and putting it in attributes would write the whole thing to
    the recorder on every change.
    """

    sessions: dict

    def as_dict(self) -> dict:
        return {"sessions": self.sessions}


class XpSessionSensor(OsrsActivityEntity, SensorEntity, RestoreEntity):
    """How many skills have a live counter, plus everything behind that.

    This is the one to point a display at: the whole picture is in its
    attributes. It is called Activity rather than anything with XP in it
    because "XP session" and "Session XP" next to each other in an entity
    picker is a trap, and one that has already been walked into.
    """

    _attr_icon = "mdi:run"

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "xp_session")

    @property
    def native_value(self) -> int:
        return self.data.get("active", 0)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            key: value
            for key, value in self.data.items()
            if key not in INTERNAL
        }

    @property
    def extra_restore_state_data(self) -> StoredSessions:
        return StoredSessions(self.data.get("sessions_raw", {}))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        stored = await self.async_get_last_extra_data()
        if stored is None:
            return
        restored = self.coordinator.engine.restore(
            stored.as_dict().get("sessions", {})
        )
        if restored:
            self.coordinator.async_republish()


class FocusSkillSensor(OsrsActivityEntity, SensorEntity):
    """The skill the screen is currently about."""

    _attr_icon = "mdi:target"

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "focus_skill")

    @property
    def native_value(self) -> str | None:
        return self.data.get("top", {}).get("key")

    @property
    def extra_state_attributes(self) -> dict:
        return self.data.get("top", {})


class SessionXpSensor(OsrsActivityEntity, SensorEntity):
    """XP gained in this sitting, across everything in focus."""

    _attr_icon = "mdi:trending-up"
    _attr_native_unit_of_measurement = "XP"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "session_xp")

    @property
    def native_value(self) -> int:
        return self.data.get("total_gained", 0)

    @property
    def extra_state_attributes(self) -> dict:
        return {"short": self.data.get("total_gained_short", "0")}


class XpPerHourSensor(OsrsActivityEntity, SensorEntity):
    """The rate, measured from the start of the sitting."""

    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = "XP/h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "xp_per_hour")

    @property
    def native_value(self) -> int:
        return self.data.get("per_hour", 0)


class CombatStyleSensor(OsrsActivityEntity, SensorEntity):
    """Attack style, or the slayer heading, while in combat."""

    _attr_icon = "mdi:sword"

    def __init__(self, coordinator: ActivityCoordinator) -> None:
        super().__init__(coordinator, "combat_style")

    @property
    def native_value(self) -> str | None:
        return self.data.get("style") or None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "combat": self.data.get("combat", False),
            "style_key": self.data.get("style_key", ""),
            "slayer_kills": self.data.get("slayer_kills", 0),
        }
