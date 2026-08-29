"""What is this player doing right now.

Skill sensors report a total: how much XP you have, not how much you just
earned. Everything interesting is a delta, and a delta needs memory. That
memory is the only state this file keeps -- which skills have a live counter,
when each was last touched, and what the total was when the counter started.
Everything else (which skill is in focus, how the bars scale, what attack style
you are using) is recomputed from scratch on every snapshot.

No Home Assistant imports on purpose. This is the part that would be the same
on any display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .const import (
    COLOUR_FALLBACK,
    COLOURS,
    COMBAT_SKILLS,
    LABELS,
    MAX_LEVEL,
    MAX_XP,
    MELEE_STYLES,
    NOT_A_STYLE,
)


def _xp_table(max_level: int = MAX_LEVEL) -> list[int]:
    """The OSRS experience table. table[99] == 13034431."""
    table = [0, 0]
    total = 0.0
    for level in range(1, max_level):
        total += math.floor(level + 300 * (2 ** (level / 7.0)))
        table.append(math.floor(total / 4))
    return table


XP_TABLE = _xp_table()


def level_of(xp: int) -> int:
    """Virtual level for an XP total; 126 is the last one the table has."""
    for level in range(len(XP_TABLE) - 1, 0, -1):
        if xp >= XP_TABLE[level]:
            return level
    return 1


def band(xp: int) -> tuple[int, int | None, int]:
    """(percent through the current level, next level, XP still to go).

    Past virtual level 126 there is no next level, so the bar runs to 200m
    instead -- that being the only target a maxed skill has left.
    """
    level = level_of(xp)
    if level >= len(XP_TABLE) - 1:
        low, high, nxt = XP_TABLE[-1], MAX_XP, None
    else:
        low, high, nxt = XP_TABLE[level], XP_TABLE[level + 1], level + 1
    span = high - low
    pct = 0 if span <= 0 else max(0, min(100, round((xp - low) * 100 / span)))
    return int(pct), nxt, max(0, high - xp)


def short(value: float) -> str:
    """XP the way the game writes it: 1.2m / 340k / 12.3k / 840."""
    if value >= 99_500_000:
        return f"{round(value / 1_000_000)}m"
    if value >= 999_500:
        return f"{value / 1_000_000:.1f}m"
    if value >= 99_950:
        return f"{round(value / 1000)}k"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(int(value))


def label_for(skill: str) -> str:
    """Four characters, which is what fits beside a bar on a 64px panel."""
    return LABELS.get(skill, skill[:4].upper())


def colour_for(skill: str) -> tuple[int, int, int]:
    return COLOURS.get(skill, COLOUR_FALLBACK)


@dataclass
class Session:
    """One skill's live counter."""

    base: int
    xp: int
    start: datetime
    last: datetime
    ticks: int = 0
    # Slayer XP arrives in a fixed amount per kill, so a run of equal chunks
    # counts kills. The moment one differs (a barrage, a mixed task, a kill that
    # lands together with something else) the division stops meaning anything
    # and we show nothing -- a wrong number is worse than no number.
    chunk: int | None = None
    uniform: bool = True

    def as_raw(self) -> list:
        """Flat form, small enough to keep in a state attribute."""
        return [
            self.base,
            self.xp,
            self.ticks,
            self.start.isoformat(timespec="seconds"),
            self.last.isoformat(timespec="seconds"),
            self.chunk or 0,
            self.uniform,
        ]

    @classmethod
    def from_raw(cls, raw: list) -> Session:
        return cls(
            base=int(raw[0]),
            xp=int(raw[1]),
            ticks=int(raw[2]),
            start=datetime.fromisoformat(raw[3]),
            last=datetime.fromisoformat(raw[4]),
            chunk=(int(raw[5]) if len(raw) > 5 and raw[5] else None),
            uniform=(bool(raw[6]) if len(raw) > 6 else True),
        )


@dataclass
class ActivityEngine:
    """Folds XP gains into per-skill sessions and reports on them."""

    window: timedelta
    focus_seconds: int
    sessions: dict[str, Session] = field(default_factory=dict)
    idle_at: datetime | None = None

    def record(
        self, skill: str, xp: int, previous: int | None, now: datetime
    ) -> bool:
        """Fold one XP change into that skill's session.

        Returns True if anything changed. Publishing is left to the caller, on
        its own tick -- see TICK_SECONDS.
        """
        session = self.sessions.get(skill)

        if session is None or now - session.last > self.window or xp < session.xp:
            # A fresh sitting. The baseline is the total from BEFORE this gain,
            # or the counter always misses its own first tick. The xp <
            # session.xp case catches a client restart: the skill sensor
            # restores from the hiscores, and those can sit lower than the live
            # value did.
            base = xp if previous is None else min(previous, xp)
            self.sessions[skill] = Session(base=base, xp=xp, start=now, last=now)
        elif xp == session.xp:
            return False
        else:
            delta = xp - session.xp
            if session.chunk is None:
                session.chunk = delta
            elif delta != session.chunk:
                session.uniform = False
            session.xp = xp
            session.last = now
            session.ticks += 1

        # XP arriving means you are not idle. Until the plugin grows a
        # "player is active again" event this is the only thing that clears it.
        self.idle_at = None
        return True

    def mark_idle(self, now: datetime) -> None:
        self.idle_at = now

    def restore(self, raw: dict) -> int:
        """Bring sessions back from a stored snapshot after a reload."""
        for skill, values in (raw or {}).items():
            try:
                self.sessions[skill] = Session.from_raw(values)
            except (TypeError, ValueError, IndexError, KeyError):
                continue
        return len(self.sessions)

    def _row(self, skill: str, session: Session, now: datetime) -> dict:
        idle = (now - session.last).total_seconds()
        gained = session.xp - session.base
        # Floor the elapsed time at a minute, or the first few seconds of a
        # session report a rate in the millions.
        elapsed = max(60.0, (now - session.start).total_seconds())
        pct, next_level, to_go = band(session.xp)
        per_hour = int(gained / elapsed * 3600)
        red, green, blue = colour_for(skill)
        return {
            "key": skill,
            "label": label_for(skill),
            "color": [red, green, blue],
            "color_hex": f"#{red:02x}{green:02x}{blue:02x}",
            "gained": gained,
            "gained_short": short(gained),
            "per_hour": per_hour,
            "per_hour_short": short(per_hour),
            "xp": session.xp,
            "xp_short": short(session.xp),
            "level": min(99, level_of(session.xp)),
            "virtual_level": level_of(session.xp),
            "pct": pct,
            "next_level": next_level,
            "to_go_short": short(to_go),
            "idle": int(idle),
            "ticks": session.ticks,
            "kills": (
                int(gained / session.chunk)
                if session.uniform and session.chunk
                else 0
            ),
        }

    def snapshot(self, now: datetime) -> dict:
        """Everything a display could want, recomputed from the sessions."""
        rows = [
            self._row(skill, session, now)
            for skill, session in self.sessions.items()
            if now - session.last <= self.window and session.xp > session.base
        ]
        rows.sort(key=lambda row: row["gained"], reverse=True)

        # What is on screen NOW. If that falls empty during a short pause, show
        # the whole window again rather than nothing.
        focus = [row for row in rows if row["idle"] <= self.focus_seconds] or rows

        top = focus[0] if focus else {}
        # Bars scale against the biggest gainer INSIDE the focus, not against an
        # absolute XP figure. That makes a combat sitting read as a ratio
        # (2:1:1 str/att/hp), and makes the same scale work for Wintertodt and
        # for Zulrah.
        top_gain = top.get("gained", 0) or 1
        for row in rows:
            row["share"] = max(1, round(row["gained"] * 100 / top_gain))

        keys = [row["key"] for row in focus]
        combat = len(focus) >= 2 and all(key in COMBAT_SKILLS for key in keys)
        style, style_key = self._style(focus, keys) if combat else ("", "")

        total = sum(row["gained"] for row in focus)
        return {
            "active": len(rows),
            "focus_n": len(focus),
            "skills": focus,
            "window_skills": rows,
            "top": top,
            "combat": combat,
            "style": style,
            "style_key": style_key,
            "slayer_kills": next(
                (row["kills"] for row in focus if row["key"] == "slayer"), 0
            ),
            "total_gained": total,
            "total_gained_short": short(total),
            "per_hour": sum(row["per_hour"] for row in focus),
            "idle": self.idle_at is not None,
            "idle_since": (
                self.idle_at.isoformat(timespec="seconds")
                if self.idle_at
                else None
            ),
            "idle_seconds": (
                int((now - self.idle_at).total_seconds()) if self.idle_at else 0
            ),
            "window": int(self.window.total_seconds()),
            "focus_seconds": self.focus_seconds,
            "last_gain": max(
                (session.last for session in self.sessions.values()), default=now
            ).isoformat(timespec="seconds"),
            "sessions_raw": {
                skill: session.as_raw()
                for skill, session in self.sessions.items()
            },
        }

    def _style(self, focus: list[dict], keys: list[str]) -> tuple[str, str]:
        """Which attack style, read off from which skills are gaining."""
        drivers = [row for row in focus if row["key"] not in NOT_A_STYLE]
        if not drivers:
            return "", ""

        # By RECENCY, not by total. Switch from attack to strength and attack
        # keeps the larger accumulated total for minutes, so "biggest gainer"
        # would stay stuck on the style you just left. What you are doing NOW is
        # whatever came in last.
        freshest = min(row["idle"] for row in drivers)
        # Controlled grants all three on the same hit, so those land within a
        # tick of each other. A few seconds of slack separates "together" from
        # "just switched".
        fresh = [row for row in drivers if row["idle"] <= freshest + 3]
        fresh_keys = [row["key"] for row in fresh]

        if "slayer" in keys:
            # Slayer overrides the attack style in the heading. You know
            # perfectly well whether you are holding an axe or a bow; what you
            # cannot see is how far along the task is.
            return "Slayin'", "slayer"
        if "ranged" in fresh_keys:
            return "RANGED", "ranged"
        if "magic" in fresh_keys:
            return "MAGIC", "magic"

        melee = tuple(
            sorted(
                key
                for key in fresh_keys
                if key in ("attack", "strength", "defence")
            )
        )
        style = MELEE_STYLES.get(melee, "MELEE")
        # A single style uses that skill's icon; controlled has no icon of its
        # own, so attack stands in for it.
        return style, (melee[0] if len(melee) == 1 else "attack")
