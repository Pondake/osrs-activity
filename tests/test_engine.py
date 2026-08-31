"""Tests for the activity engine.

The engine has no Home Assistant imports, so these run with plain pytest and no
test harness. Loaded through a stub package so the relative imports in
engine.py resolve without pulling in the integration's __init__.

    pytest
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "osrs_activity"


def _load():
    package = types.ModuleType("_oa")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_oa"] = package
    for name in ("const", "engine"):
        spec = importlib.util.spec_from_file_location(
            f"_oa.{name}", COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_oa.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["_oa.engine"]


engine = _load()
T0 = datetime(2026, 8, 29, 12, 0, 0)


def make(window_minutes: float = 5, focus_seconds: int = 25):
    return engine.ActivityEngine(
        window=timedelta(minutes=window_minutes), focus_seconds=focus_seconds
    )


def test_xp_table_matches_the_game():
    assert engine.XP_TABLE[99] == 13034431
    assert engine.XP_TABLE[92] == 6517253  # half of 99, the well-known one
    assert engine.level_of(13034431) == 99
    assert engine.level_of(13034430) == 98


def test_short_formats_like_the_game():
    assert engine.short(840) == "840"
    assert engine.short(12340) == "12.3k"
    assert engine.short(340_000) == "340k"
    assert engine.short(1_200_000) == "1.2m"
    assert engine.short(120_000_000) == "120m"


def test_first_gain_counts():
    """The baseline is the total from before the gain, not after it."""
    eng = make()
    eng.record("mining", 1000, 900, T0)
    snapshot = eng.snapshot(T0)
    assert snapshot["active"] == 1
    assert snapshot["top"]["gained"] == 100


def test_a_gap_longer_than_the_window_starts_over():
    eng = make(window_minutes=5)
    eng.record("mining", 1000, 900, T0)
    later = T0 + timedelta(minutes=6)
    eng.record("mining", 1500, 1400, later)
    assert eng.snapshot(later)["top"]["gained"] == 100


def test_expired_skills_drop_out():
    eng = make(window_minutes=5)
    eng.record("mining", 1000, 900, T0)
    assert eng.snapshot(T0 + timedelta(minutes=6))["active"] == 0


def test_lower_xp_after_a_restart_does_not_go_negative():
    """The skill sensor restores from the hiscores, which can lag the live value."""
    eng = make()
    eng.record("mining", 5000, 4900, T0)
    eng.record("mining", 4000, None, T0 + timedelta(seconds=5))
    assert eng.snapshot(T0 + timedelta(seconds=5))["total_gained"] == 0


def test_focus_drops_what_you_stopped_doing():
    eng = make(focus_seconds=25)
    eng.record("attack", 1000, 900, T0)
    eng.record("strength", 1000, 900, T0)
    later = T0 + timedelta(seconds=40)
    eng.record("mining", 1000, 900, later)
    snapshot = eng.snapshot(later)
    assert [row["key"] for row in snapshot["skills"]] == ["mining"]
    # ...but they keep their counters inside the window.
    assert len(snapshot["window_skills"]) == 3


def test_focus_falls_back_to_the_window_during_a_pause():
    eng = make(focus_seconds=25)
    eng.record("mining", 1000, 900, T0)
    snapshot = eng.snapshot(T0 + timedelta(seconds=60))
    assert snapshot["focus_n"] == 1


def test_melee_style_is_read_from_which_skills_gain():
    eng = make()
    eng.record("strength", 1000, 900, T0)
    eng.record("hitpoints", 1000, 970, T0)
    snapshot = eng.snapshot(T0)
    assert snapshot["combat"] is True
    assert snapshot["style"] == "AGGRESSIVE"


def test_style_follows_the_most_recent_skill_not_the_biggest():
    """Switch attack -> strength and attack still has more accumulated XP."""
    eng = make()
    eng.record("attack", 10_000, 0, T0)
    eng.record("hitpoints", 3000, 0, T0)
    later = T0 + timedelta(seconds=20)
    eng.record("strength", 100, 0, later)
    eng.record("hitpoints", 3030, 3000, later)
    assert eng.snapshot(later)["style"] == "AGGRESSIVE"


def test_slayer_overrides_the_attack_style():
    eng = make()
    eng.record("strength", 1000, 900, T0)
    eng.record("slayer", 500, 400, T0)
    snapshot = eng.snapshot(T0)
    assert snapshot["style"] == "Slayin'"
    assert snapshot["style_key"] == "slayer"


def slaying(**kwargs):
    """An engine mid-task, plus the task the game would be reporting."""
    eng = make()
    eng.record("strength", 1000, 900, T0)
    eng.record("slayer", 500, 400, T0)
    return eng, engine.SlayerTask(**kwargs)


def test_the_task_names_the_heading():
    eng, task = slaying(name="Bloodvelds", remaining=42, initial=150)
    snapshot = eng.snapshot(T0, task)
    assert snapshot["style"] == "BLOODVELDS"
    assert snapshot["style_key"] == "slayer"
    assert snapshot["slayer"]["remaining"] == 42


def test_a_long_task_name_is_cut_to_the_heading_line():
    eng, task = slaying(name="Aberrant spectres", remaining=8, initial=120)
    # Whole words only, not a hard 11-char slice -- see test_task_label_*.
    assert eng.snapshot(T0, task)["style"] == "ABERRANT"


def test_no_task_keeps_the_old_heading():
    """The plugin toggle is off by default, so this is the common case."""
    eng, _ = slaying(name="unused")
    snapshot = eng.snapshot(T0)
    assert snapshot["style"] == "Slayin'"
    assert snapshot["slayer"] == {}


def test_task_progress_is_measured_against_what_was_assigned():
    eng, task = slaying(name="Gargoyles", remaining=30, initial=120)
    row = eng.snapshot(T0, task)["slayer"]
    assert row["done"] == 90
    assert row["pct"] == 75


def test_a_task_picked_up_mid_way_reports_no_percentage():
    """Logging in part-way through leaves nothing to measure against."""
    eng, task = slaying(name="Kalphite", remaining=30, initial=0)
    row = eng.snapshot(T0, task)["slayer"]
    assert row["remaining"] == 30
    assert (row["done"], row["pct"]) == (0, 0)


def test_a_slow_kill_does_not_drop_slayer_out_of_focus():
    """The bug report: a tough target grants melee XP every hit, slayer XP
    only on the kill -- so slayer used to age out of focus first, and the
    heading flipped to plain melee mid-fight even though nothing changed."""
    eng = make(window_minutes=5, focus_seconds=25)
    eng.record("strength", 1000, 900, T0)
    eng.record("slayer", 500, 400, T0)

    later = T0 + timedelta(seconds=120)  # past focus_seconds, well under window
    eng.record("strength", 1200, 1000, later)  # melee keeps landing hits
    snapshot = eng.snapshot(later)
    assert snapshot["style"] == "Slayin'"
    assert snapshot["style_key"] == "slayer"


def test_a_slow_kill_still_expires_past_the_session_window():
    eng = make(window_minutes=5, focus_seconds=25)
    eng.record("strength", 1000, 900, T0)
    eng.record("slayer", 500, 400, T0)

    later = T0 + timedelta(minutes=6)  # past the session window itself
    eng.record("strength", 1200, 1000, later)
    snapshot = eng.snapshot(later)
    assert snapshot["style"] != "Slayin'"


def test_genuinely_stopping_does_not_strand_slayer_alone_in_focus():
    """The bug report: task done, went idle, and the screen fell back to a
    lone "SLAYER" skill view instead of the task screen or the same
    whole-window fallback everything else gets. Slayer's grace period is
    only meant to cover a slow KILL -- borrowed from evidence that some
    other combat skill is still landing hits. With nothing landing at all,
    it must age out together with melee, not outlive it alone."""
    eng = make(window_minutes=5, focus_seconds=25)
    eng.record("strength", 1000, 900, T0)
    eng.record("slayer", 500, 400, T0)

    later = T0 + timedelta(seconds=60)  # past focus_seconds; nothing since
    snapshot = eng.snapshot(later)
    keys = {row["key"] for row in snapshot["skills"]}
    assert keys == {"strength", "slayer"}  # fell back together, not solo
    assert snapshot["combat"] is True
    assert snapshot["style_key"] == "slayer"


def test_every_way_of_saying_there_is_no_task():
    for absent in ("None", "null", "", "  ", "unknown", "unavailable", None, 0):
        assert engine.task_name(absent) is None, absent
    assert engine.task_name(" Fire giants ") == "Fire giants"


def test_task_label_drops_the_filler_word():
    assert engine.task_label("The Whisperer") == "WHISPERER"
    assert engine.task_label("The Giant Mole") == "GIANT MOLE"


def test_task_label_cuts_at_a_word_boundary_not_mid_word():
    """The bug report: ABERRANT SP reads as broken, not as a name."""
    assert engine.task_label("Aberrant spectres") == "ABERRANT"
    assert engine.task_label("Deranged Archaeologist") == "DERANGED"


def test_task_label_uses_the_curated_abbreviation_when_there_is_one():
    assert engine.task_label("Dagannoth Kings") == "DKS"
    assert engine.task_label("The Thermonuclear Smoke Devil") == "TSD"


# Every task name RuneLite's own Slayer plugin can produce (net.runelite.
# client.plugins.slayer.Task, checked 2026-08-31). A snapshot, not a live
# fetch -- if Jagex ships a new slayer task, re-run the same check against
# the current Task.java and extend TASK_ABBREVIATIONS with whatever this
# then flags.
ALL_SLAYER_TASK_NAMES = [
    "Aberrant spectres", "Abyssal demons", "Ankou", "Aquanites", "Araxxor",
    "Araxytes", "Aviansies", "Bandits", "Banshees", "Barrows Brothers",
    "Basilisks", "Bats", "Bears", "Birds", "Black Knights", "Black demons",
    "Black dragons", "Bloodveld", "Blue dragons", "Brine rats", "Callisto",
    "Catablepon", "Cave bugs", "Cave crawlers", "Cave horrors", "Cave kraken",
    "Cave slimes", "Cerberus", "Chaos druids", "Cockatrice",
    "Commander Zilyana", "Cows", "Crabs", "Crawling hands",
    "Crazy Archaeologists", "Crocodiles", "Custodian Stalkers", "Dagannoth",
    "Dagannoth Kings", "Dark beasts", "Dark warriors",
    "Deranged Archaeologist", "Dogs", "Drakes", "Duke Sucellus",
    "Dust devils", "Dwarves", "Earth warriors", "Elves", "Ents",
    "Fever spiders", "Fire giants", "Fleshcrawlers",
    "Fossil island wyverns", "Frost dragons", "Gargoyles",
    "General Graardor", "Ghosts", "Ghouls", "Goblins", "Greater demons",
    "Green dragons", "Gryphons", "Harpie bug swarms", "Hellhounds",
    "Hill giants", "Hobgoblins", "Hydras", "Ice giants", "Ice warriors",
    "Icefiends", "Infernal mages", "Jellies", "Jungle horrors",
    "K'ril Tsutsaroth", "Kalphites", "Killerwatts", "Kree'arra", "Kurask",
    "Lava Dragons", "Lesser Nagua", "Lesser demons", "Lizardmen", "Lizards",
    "Magic axes", "Mammoths", "Metal dragons", "Minotaurs", "Mogres",
    "Molanisks", "Monkeys", "Moss giants", "Mutated zygomites", "Nechryael",
    "Ogres", "Otherworldly beings", "Pirates", "Pyrefiends", "Rats",
    "Red dragons", "Revenants", "Rockslugs", "Rogues", "Sarachnis",
    "Scabarites", "Scorpia", "Scorpions", "Sea snakes", "Shades",
    "Shadow warriors", "Skeletal wyverns", "Skeletons", "Smoke devils",
    "Sourhogs", "Spiders", "Spiritual creatures", "Suqahs", "Terror dogs",
    "The Abyssal Sire", "The Alchemical Hydra", "The Cave Kraken Boss",
    "The Chaos Elemental", "The Chaos Fanatic", "The Giant Mole",
    "The Grotesque Guardians", "The Kalphite Queen", "The King Black Dragon",
    "The Leviathan", "The Maggot King", "The Phantom Muspah",
    "The Shellbane Gryphon", "The Thermonuclear Smoke Devil",
    "The Whisperer", "Trolls", "Turoth", "TzKal-Zuk", "TzTok-Jad", "Tzhaar",
    "Vampyres", "Vardorvis", "Venators", "Venenatis", "Vet'ion", "Vorkath",
    "Wall beasts", "Warped Creatures", "Waterfiends", "Werewolves", "Wolves",
    "Wyrms", "Zombies", "Zulrah",
]


def test_every_real_task_name_fits_the_heading():
    for name in ALL_SLAYER_TASK_NAMES:
        label = engine.task_label(name)
        assert len(label) <= engine.TASK_LABEL_MAX, (name, label)


def test_no_two_real_task_names_collide_once_trimmed():
    seen = {}
    collisions = []
    for name in ALL_SLAYER_TASK_NAMES:
        label = engine.task_label(name)
        if label in seen and seen[label] != name:
            collisions.append((seen[label], name, label))
        seen[label] = name
    assert not collisions


def test_prayer_does_not_break_combat():
    eng = make()
    eng.record("strength", 1000, 900, T0)
    eng.record("prayer", 200, 150, T0)
    assert eng.snapshot(T0)["combat"] is True


def test_a_non_combat_skill_breaks_combat():
    eng = make()
    eng.record("strength", 1000, 900, T0)
    eng.record("mining", 1000, 900, T0)
    assert eng.snapshot(T0)["combat"] is False


def test_uniform_chunks_count_kills():
    """Three kills at 40 XP each, starting from a total of 100."""
    eng = make()
    for i in range(3):
        eng.record("slayer", 140 + 40 * i, 100 + 40 * i, T0)
    assert eng.snapshot(T0)["slayer_kills"] == 3


def test_one_odd_chunk_stops_the_kill_count():
    eng = make()
    eng.record("slayer", 140, 100, T0)
    eng.record("slayer", 180, 140, T0)
    eng.record("slayer", 217, 180, T0)  # a barrage, or two kills at once
    assert eng.snapshot(T0)["slayer_kills"] == 0


def test_idle_is_cleared_by_the_next_gain():
    """The fallback, for a client that does not report coming back."""
    eng = make()
    eng.record("mining", 1000, 900, T0)
    eng.mark_idle(T0 + timedelta(seconds=30))
    assert eng.snapshot(T0 + timedelta(seconds=30))["idle"] is True
    eng.record("mining", 1100, 1000, T0 + timedelta(seconds=40))
    assert eng.snapshot(T0 + timedelta(seconds=40))["idle"] is False


def test_the_active_event_clears_idle_without_any_xp():
    """Banking and walking grant nothing, which is the whole point of it."""
    eng = make()
    eng.record("mining", 1000, 900, T0)
    eng.mark_idle(T0 + timedelta(seconds=30), ticks=50)
    assert eng.snapshot(T0 + timedelta(seconds=30))["idle_ticks"] == 50

    eng.mark_active(T0 + timedelta(seconds=90), ticks=150)
    snapshot = eng.snapshot(T0 + timedelta(seconds=90))
    assert snapshot["idle"] is False
    assert snapshot["idle_ticks"] == 0
    # The plugin's count, not the clock: 150 ticks at 0.6s.
    assert snapshot["last_idle_seconds"] == 90


def test_coming_back_without_a_tick_count_falls_back_to_the_clock():
    eng = make()
    eng.record("mining", 1000, 900, T0)
    eng.mark_idle(T0)
    eng.mark_active(T0 + timedelta(seconds=45))
    assert eng.snapshot(T0)["last_idle_seconds"] == 45


def test_becoming_active_when_never_idle_changes_nothing():
    eng = make()
    eng.mark_active(T0, ticks=999)
    snapshot = eng.snapshot(T0)
    assert snapshot["idle"] is False
    assert snapshot["last_idle_seconds"] == 0


def test_logging_out_ends_the_sitting():
    """The window forgives a pause at the rocks; it does not forgive a logout."""
    eng = make(window_minutes=5)
    eng.record("mining", 1000, 900, T0)
    eng.mark_idle(T0)
    assert eng.end() == 1

    snapshot = eng.snapshot(T0)
    assert snapshot["active"] == 0
    assert snapshot["idle"] is False

    # And logging back in starts from zero rather than resuming.
    eng.record("mining", 1100, 1000, T0 + timedelta(seconds=30))
    assert eng.snapshot(T0 + timedelta(seconds=30))["total_gained"] == 100


def test_ending_an_empty_engine_is_harmless():
    assert make().end() == 0


def test_sessions_survive_a_round_trip():
    eng = make()
    eng.record("mining", 1000, 900, T0)
    eng.record("slayer", 140, 100, T0)
    raw = eng.snapshot(T0)["sessions_raw"]

    restored = make()
    assert restored.restore(raw) == 2
    assert restored.snapshot(T0)["total_gained"] == eng.snapshot(T0)["total_gained"]


def test_bars_scale_against_the_biggest_gainer_in_focus():
    eng = make()
    eng.record("strength", 200, 0, T0)
    eng.record("attack", 100, 0, T0)
    rows = {row["key"]: row["share"] for row in eng.snapshot(T0)["window_skills"]}
    assert rows["strength"] == 100
    assert rows["attack"] == 50


def test_a_maxed_skill_aims_at_200m():
    pct, next_level, to_go = engine.band(199_000_000)
    assert next_level is None
    assert to_go == 1_000_000
    assert pct > 90
