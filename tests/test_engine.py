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
    # Eleven characters is what is left beside the count on a 64px panel.
    assert eng.snapshot(T0, task)["style"] == "ABERRANT SP"


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


def test_every_way_of_saying_there_is_no_task():
    for absent in ("None", "null", "", "  ", "unknown", "unavailable", None, 0):
        assert engine.task_name(absent) is None, absent
    assert engine.task_name(" Fire giants ") == "Fire giants"


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
