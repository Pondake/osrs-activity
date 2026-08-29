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
    eng = make()
    eng.record("mining", 1000, 900, T0)
    eng.mark_idle(T0 + timedelta(seconds=30))
    assert eng.snapshot(T0 + timedelta(seconds=30))["idle"] is True
    eng.record("mining", 1100, 1000, T0 + timedelta(seconds=40))
    assert eng.snapshot(T0 + timedelta(seconds=40))["idle"] is False


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
