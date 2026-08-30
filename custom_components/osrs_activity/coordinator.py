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
    PING_TIMEOUT,
    RUNELITE_DOMAIN,
    SIGNAL_UPDATE,
    TICK_SECONDS,
    VITALS,
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
# The RuneLite status sensor for a player, which carries last_ping_time.
STATUS_MARKER = "_player_status"


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
        self._status_uid = (
            f"{RUNELITE_DOMAIN}_{sanitize(username)}{STATUS_MARKER}"
        )
        self._entities: dict[str, str] = {}  # entity_id -> skill
        self._status_entity: str | None = None
        self._vitals: dict[str, str] = {}  # role -> entity_id
        self._unsub_states = None
        self._unsubs: list = []
        self._icons: set[str] = set()
        self._icon_dir = Path(hass.config.path("www")) / ICON_DIR
        self._last_signature: tuple | None = None
        self._was_online: bool | None = None

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
        status = None
        prefix = f"{RUNELITE_DOMAIN}_{sanitize(self.username)}"
        wanted = {
            template.format(prefix=prefix): role
            for role, template in VITALS.items()
        }
        vitals: dict[str, str] = {}
        for entry in registry.entities.values():
            if entry.platform != RUNELITE_DOMAIN or not entry.unique_id:
                continue
            if entry.unique_id == self._status_uid:
                status = entry.entity_id
                continue
            if entry.unique_id in wanted:
                vitals[wanted[entry.unique_id]] = entry.entity_id
                # skill_hitpoints is also a skill, so no continue here.
            if not entry.unique_id.startswith(self._prefix):
                continue
            skill = entry.unique_id[len(self._prefix):]
            if skill and skill != SKILL_TOTAL:
                found[entry.entity_id] = skill

        self._vitals = vitals
        if found == self._entities and status == self._status_entity:
            return

        self._entities = found
        self._status_entity = status
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        watched = list(found) + ([status] if status else [])
        if watched:
            self._unsub_states = async_track_state_change_event(
                self.hass, watched, self._handle_state
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
            # The status sensor is watched too, so a login shows up without
            # waiting for the tick.
            if event.data["entity_id"] == self._status_entity:
                self._publish()
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
        # Liveness first: logging out ends the sitting, and that has to happen
        # before the snapshot or the counters survive into it.
        online, ping = self._liveness()
        if self._was_online and not online:
            ended = self.engine.end()
            if ended:
                _LOGGER.debug(
                    "%s: logged out, dropped %d counter(s)", self.username, ended
                )
        self._was_online = online

        data = self.engine.snapshot(datetime.now())
        self._decorate(data, online, ping)

        signature = (
            tuple(
                (row["key"], row["gained"], row["ticks"])
                for row in data["window_skills"]
            ),
            data["idle"],
            data["online"],
            data["window"],
            tuple(row["key"] for row in data["skills"]),
            data["style"],
        )
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature
        self.data = data
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry_id}")

    def _decorate(self, data: dict, online: bool, ping: str | None) -> None:
        """Add the icon paths. The engine stays unaware of where files live."""
        for row in data["window_skills"]:
            row["icon_path"] = self._icon_path(row["key"])
            row["icon_url"] = self._icon_url(row["key"])
        data["style_icon"] = self._icon_path(data["style_key"])
        data["style_icon_url"] = self._icon_url(data["style_key"])
        data["account"] = self.username
        data["online"], data["last_ping"] = online, ping
        data["health_pct"] = self._vital("health", "health_max")
        data["prayer_pct"] = self._vital("prayer", "prayer_max")

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


    def _vital(self, now_role: str, max_role: str) -> int | None:
        """Percent full, or None when this player has no such sensor.

        The maximum is the skill LEVEL, not its XP -- 99 hitpoints means 99
        health, and the skill sensor carries the level as an attribute.
        """
        now_id = self._vitals.get(now_role)
        max_id = self._vitals.get(max_role)
        if not now_id or not max_id:
            return None
        current = self.hass.states.get(now_id)
        ceiling = self.hass.states.get(max_id)
        if current is None or ceiling is None:
            return None
        try:
            value = float(current.state)
            top = float(ceiling.attributes.get("level"))
        except (TypeError, ValueError):
            return None
        if top <= 0:
            return None
        return max(0, min(100, round(value / top * 100)))

    def _liveness(self) -> tuple[bool, str | None]:
        """Whether the plugin is still pushing, and when it last did."""
        if not self._status_entity:
            return False, None
        state = self.hass.states.get(self._status_entity)
        if state is None:
            return False, None
        ping = state.attributes.get("last_ping_time")
        if not ping:
            return False, None
        try:
            seen = datetime.fromisoformat(ping)
        except (TypeError, ValueError):
            return False, None
        age = (datetime.now(seen.tzinfo) - seen).total_seconds()
        return age <= PING_TIMEOUT, ping


def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
