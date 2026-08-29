"""Wiring between Home Assistant and the activity engine.

Three inputs: the RuneLite skill sensors changing, the plugin's idle event, and
a clock. One output: a snapshot, dispatched to the entities when it differs
from the last one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    EVENT_IDLE,
    ICON_BLANK,
    ICON_DIR,
    RUNELITE_DOMAIN,
    SIGNAL_UPDATE,
    TICK_SECONDS,
)
from .engine import ActivityEngine

_LOGGER = logging.getLogger(__name__)

# The skill sensors are named runelite_<user>_skill_<skill>, lowercased, with
# spaces turned into underscores. Matching on the unique_id rather than the
# entity_id means a renamed entity keeps working, and it tells us the skill
# without parsing a display name.
SKILL_MARKER = "_skill_"
# Overall XP. It moves on every gain in every skill, so it would report as a
# skill that is always active.
SKILL_TOTAL = "total"


def sanitize(text: str) -> str:
    """Match the RuneLite integration's own unique_id normalisation."""
    return text.replace(" ", "_").lower()


class ActivityCoordinator:
    """Owns the engine, feeds it, and publishes what comes out."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        username: str,
        window_minutes: float,
        focus_seconds: int,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.username = username
        self.engine = ActivityEngine(
            window=timedelta(minutes=window_minutes),
            focus_seconds=focus_seconds,
        )
        self.data: dict = {}
        self._prefix = f"{RUNELITE_DOMAIN}_{sanitize(username)}{SKILL_MARKER}"
        self._entities: dict[str, str] = {}  # entity_id -> skill
        self._unsub_states = None
        self._unsubs: list = []
        self._icons: set[str] = set()
        self._icon_dir = Path(hass.config.path("www")) / ICON_DIR
        self._last_signature: tuple | None = None

    # -- lifecycle ---------------------------------------------------------

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(self._scan_icons)
        self._resubscribe()

        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_IDLE, self._handle_idle)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._handle_tick, timedelta(seconds=TICK_SECONDS)
            )
        )
        self._publish(force=True)

    @callback
    def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None

    # -- discovery ---------------------------------------------------------

    @callback
    def _resubscribe(self) -> None:
        """Find this player's skill sensors and listen to exactly those.

        Rescanned whenever the entity registry changes, so a client that comes
        online later (or a skill that did not exist yet -- Sailing arrived
        mid-2026) is picked up without a restart.
        """
        registry = er.async_get(self.hass)
        found: dict[str, str] = {}
        for entry in registry.entities.values():
            if entry.platform != RUNELITE_DOMAIN or not entry.unique_id:
                continue
            if not entry.unique_id.startswith(self._prefix):
                continue
            skill = entry.unique_id[len(self._prefix):]
            if skill and skill != SKILL_TOTAL:
                found[entry.entity_id] = skill

        if found == self._entities:
            return

        self._entities = found
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        if found:
            self._unsub_states = async_track_state_change_event(
                self.hass, list(found), self._handle_state
            )
        _LOGGER.debug(
            "%s: tracking %d skill sensors", self.username, len(found)
        )

    @property
    def tracked_skills(self) -> int:
        return len(self._entities)

    def _scan_icons(self) -> None:
        """Which skill icons are on disk, resolved once rather than per render.

        The Pixoo integration opens these with PIL and only catches template
        and network errors, so a path that does not exist takes down the whole
        page. Resolving here means a skill without an icon falls back to the
        transparent stand-in instead.
        """
        try:
            self._icons = {
                path.stem for path in self._icon_dir.glob("*.png")
            }
        except OSError:
            self._icons = set()

    @callback
    def async_republish(self) -> None:
        """Recompute now, from outside. Used after sessions are restored."""
        self._publish(force=True)

    async def async_refresh_icons(self) -> None:
        await self.hass.async_add_executor_job(self._scan_icons)
        self._publish(force=True)

    # -- inputs ------------------------------------------------------------

    @callback
    def _handle_registry(self, event: Event) -> None:
        if event.data.get("action") in ("create", "remove", "update"):
            self._resubscribe()

    @callback
    def _handle_state(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        skill = self._entities.get(event.data["entity_id"])
        if skill is None:
            return
        xp = _as_int(new_state.state)
        if xp is None:
            return
        old_state = event.data.get("old_state")
        previous = _as_int(old_state.state) if old_state else None
        # Deliberately no publish here. A single hit in combat lands XP in four
        # skills within 80ms; publishing each of those means four renders and a
        # queue that never drains. The tick folds them into one.
        self.engine.record(skill, xp, previous, datetime.now())

    @callback
    def _handle_idle(self, event: Event) -> None:
        """The plugin says the player has stopped doing anything.

        How long you have to stand still first is the Idle delay in the
        RuneLite plugin's own panel. There is no threshold here, so if it fires
        too eagerly that setting is where to change it.
        """
        self.engine.mark_idle(datetime.now())
        self._publish()

    @callback
    def _handle_tick(self, _now) -> None:
        self._publish()

    # -- output ------------------------------------------------------------

    @callback
    def _publish(self, force: bool = False) -> None:
        """Recompute, and only tell anyone if something actually changed.

        Without this every tick would write a state, because idle seconds and
        XP per hour keep moving even when nothing happened -- which is a
        recorder row and a panel redraw every couple of seconds for no reason.
        """
        data = self.engine.snapshot(datetime.now())
        self._decorate(data)

        signature = (
            tuple(
                (row["key"], row["gained"], row["ticks"])
                for row in data["window_skills"]
            ),
            data["idle"],
            data["window"],
            tuple(row["key"] for row in data["skills"]),
            data["style"],
        )
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature
        self.data = data
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry_id}")

    def _decorate(self, data: dict) -> None:
        """Add the icon paths. The engine stays unaware of where files live."""
        for row in data["window_skills"]:
            row["icon_path"] = self._icon_path(row["key"])
            row["icon_url"] = self._icon_url(row["key"])
        data["style_icon"] = self._icon_path(data["style_key"])
        data["style_icon_url"] = self._icon_url(data["style_key"])
        data["account"] = self.username

    def _resolve(self, skill: str) -> str | None:
        """The icon for a skill, or the transparent stand-in, or nothing.

        Never a path that does not exist. A consumer that opens the file gets
        either a picture or one transparent pixel, and a skill this integration
        has no icon for draws nothing rather than killing the page.
        """
        if skill and skill in self._icons:
            return f"{skill}.png"
        if ICON_BLANK in self._icons:
            return f"{ICON_BLANK}.png"
        return None

    def _icon_path(self, skill: str) -> str | None:
        name = self._resolve(skill)
        return str(self._icon_dir / name) if name else None

    def _icon_url(self, skill: str) -> str | None:
        name = self._resolve(skill)
        return f"/local/{ICON_DIR}/{name}" if name else None


def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
