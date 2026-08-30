"""Constants for the OSRS Activity integration."""

from __future__ import annotations

DOMAIN = "osrs_activity"
RUNELITE_DOMAIN = "runelite"

CONF_USERNAME = "username"
CONF_WINDOW_MINUTES = "window_minutes"
CONF_FOCUS_SECONDS = "focus_seconds"

# How long a skill keeps its counter after the last gain, and how long the XP
# screen stays up after you stop. Doubles as the reset threshold: come back
# later than this and the next gain starts a fresh session. One number for both
# on purpose -- then "gained" always means exactly what it says, the XP of this
# sitting.
DEFAULT_WINDOW_MINUTES = 5.0

# What is happening RIGHT NOW, which is a different question. Switch from combat
# to mining and the combat rows drop out after this, not after the whole window.
# If focus falls empty during a short pause we fall back to the whole window --
# an empty screen is worse than a slightly stale one.
DEFAULT_FOCUS_SECONDS = 25

# How often the state is recomputed. Every publish is folded into this tick
# rather than fired per gain: one hit in combat grants XP in four skills inside
# 80ms, and publishing each of those separately means four state changes, four
# renders, and a queue that never drains.
TICK_SECONDS = 2

SIGNAL_UPDATE = f"{DOMAIN}_update"

EVENT_IDLE = "runelite_idle_notify"

# How long after the plugin's last push the player still counts as logged in.
#
# Read from last_ping_time on the RuneLite status sensor rather than from that
# sensor's own state. The state also depends on the plugin reporting a usable
# world number, and a build in August 2026 stopped sending one, which left it
# reading False for a player who was demonstrably online. A ping has no such
# dependency. last_reported is no substitute: Home Assistant polls the whole
# platform every 30 seconds, so a logged-out account still looks fresh.
#
# 180s against the plugin's own 120s logout timer, so a slow push does not
# flap the sensor.
PING_TIMEOUT = 180

# Health and prayer come from the RuneLite integration too, and this already
# knows which player it is following -- so it looks them up rather than asking
# for four more entity pickers on every display.
#
# Read at publish time and deliberately NOT part of the change signature:
# health moves on almost every tick of a fight, and letting that force a
# publish would mean a redraw per hit. It rides along with the next publish
# instead, which during combat is a second or two away anyway.
VITALS = {
    "health": "{prefix}_health",
    "health_max": "{prefix}_skill_hitpoints",
    "prayer": "{prefix}_prayer",
    "prayer_max": "{prefix}_skill_prayer",
}

MAX_XP = 200_000_000
MAX_LEVEL = 126

ICON_DIR = "osrs_activity/icons"
ICON_BOX = 25
# Stem of the 1x1 transparent stand-in written alongside the icons.
ICON_BLANK = "blank"

# Skills in game order. Sailing is included; it shipped in 2026 and the wiki
# icon exists, so anyone on a client that reports it gets it for free.
SKILLS: tuple[str, ...] = (
    "attack", "strength", "defence", "hitpoints", "ranged", "prayer", "magic",
    "cooking", "woodcutting", "fletching", "fishing", "firemaking", "crafting",
    "smithing", "mining", "herblore", "agility", "thieving", "slayer",
    "farming", "runecraft", "hunter", "construction", "sailing",
)

# What counts as combat. Prayer belongs here: it ticks along while you pray,
# and a prayer bonus does not turn a fight into something else.
COMBAT_SKILLS = frozenset({
    "attack", "strength", "defence", "hitpoints", "ranged", "magic", "prayer",
    "slayer",
})

# In combat but says nothing about WHICH attack style. These tick along under
# every style, so they must not drive the style guess.
NOT_A_STYLE = frozenset({"hitpoints", "prayer", "slayer"})

# The melee styles as the game names them, read off from which of the three
# gain. That is exactly how attack style works, so this is read rather than
# guessed.
MELEE_STYLES: dict[tuple[str, ...], str] = {
    ("attack",): "ACCURATE",
    ("strength",): "AGGRESSIVE",
    ("defence",): "DEFENSIVE",
    ("attack", "defence", "strength"): "CONTROLLED",
}

# Four characters is what fits beside a bar on a 64px panel (PICO_8 is 4px per
# character). Without exceptions the label is key[:4].upper(), and for exactly
# the combat skills that reads as nonsense: ATTA / STRE / DEFE. Those get their
# usual OSRS abbreviation; the rest truncate fine (HERB, SMIT, CRAF, FLET).
LABELS: dict[str, str] = {
    "hitpoints": "HP", "attack": "ATT", "strength": "STR", "defence": "DEF",
    "ranged": "RNG", "magic": "MAG", "mining": "MINE", "fishing": "FISH",
    "farming": "FARM", "hunter": "HUNT", "runecraft": "RUNE",
}

# One colour per skill, chosen for telling them APART inside a group that runs
# together -- not for fidelity to the wiki. The combat set is the one most often
# active at the same time, so those sit far apart; the same was done for the
# skills that climb together at Wintertodt or in a minigame. On 64px over a dark
# brown everything has to stay saturated and light, so no deep shades.
COLOURS: dict[str, tuple[int, int, int]] = {
    "hitpoints": (230, 70, 70),
    "attack": (235, 140, 50),
    "strength": (90, 205, 90),
    "defence": (95, 150, 235),
    "ranged": (60, 200, 180),
    "magic": (165, 120, 240),
    "prayer": (235, 225, 150),
    "runecraft": (225, 195, 95),
    "construction": (195, 155, 115),
    "agility": (95, 175, 225),
    "herblore": (70, 195, 110),
    "thieving": (160, 115, 190),
    "crafting": (200, 155, 105),
    "fletching": (135, 205, 140),
    "slayer": (150, 150, 160),
    "hunter": (170, 145, 90),
    "mining": (150, 175, 195),
    "smithing": (200, 145, 95),
    "fishing": (110, 195, 215),
    "cooking": (205, 95, 150),
    "firemaking": (245, 125, 45),
    "woodcutting": (125, 170, 85),
    "farming": (120, 210, 120),
    "sailing": (80, 170, 225),
}

# OSRS gold, for a skill this file has never heard of.
COLOUR_FALLBACK = (255, 152, 31)
