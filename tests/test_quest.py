"""Tests for the quest half of the engine.

Same stub loading as test_engine.py: the engine has no Home Assistant imports,
so plain pytest is enough.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "osrs_activity"


def _load():
    package = types.ModuleType("_oaq")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_oaq"] = package
    for name in ("const", "engine"):
        spec = importlib.util.spec_from_file_location(
            f"_oaq.{name}", COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_oaq.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["_oaq.const"], sys.modules["_oaq.engine"]


const, engine = _load()
T0 = datetime(2026, 9, 16, 20, 0, 0)


def make(window_minutes: float = 5, focus_seconds: int = 25):
    return engine.ActivityEngine(
        window=timedelta(minutes=window_minutes), focus_seconds=focus_seconds
    )


def quest(name="Dragon Slayer II", state="IN_PROGRESS", stage=10, **extra):
    return engine.Quest(name=name, state=state, stage=stage, **extra)


# -- wrapping ---------------------------------------------------------------


def test_a_short_name_is_one_line_upper_cased():
    assert engine.wrap_name("Cook's Assistant") == ["COOK'S", "ASSISTANT"]
    assert engine.wrap_name("Dragon Slayer") == ["DRAGON SLAYER"]


def test_wrapping_breaks_on_words_and_never_past_the_width():
    lines = engine.wrap_name("Desert Treasure II - The Fallen Empire")
    assert lines == ["DESERT TREASURE", "II - THE FALLEN", "EMPIRE"]
    assert all(len(line) <= const.QUEST_LINE_MAX for line in lines)


def test_wrapping_never_returns_more_lines_than_the_screen_has():
    lines = engine.wrap_name("One Two Three Four Five Six Seven Eight Nine Ten")
    assert len(lines) == const.QUEST_LINES_MAX


def test_a_word_longer_than_a_line_is_cut_rather_than_overflowing():
    lines = engine.wrap_name("Supercalifragilisticexpialidocious quest")
    assert lines[0] == "SUPERCALIFRAGIL"
    assert all(len(line) <= const.QUEST_LINE_MAX for line in lines)


# -- the row ----------------------------------------------------------------


def test_the_row_carries_the_quest_and_its_progress():
    row = quest(points=150, completed=120, total=170).as_row()
    assert row["quest"] == "Dragon Slayer II"
    assert row["lines"] == ["DRAGON SLAYER", "II"]
    assert row["in_progress"] is True
    assert row["finished"] is False
    assert row["pct"] == 71


def test_no_quest_means_an_empty_row_and_nothing_flagged():
    snapshot = make().snapshot(T0)
    assert snapshot["quest"] == {}
    assert snapshot["questing"] is False
    assert snapshot["celebrating"] is False
    assert snapshot["quest_complete"] == {}


# -- questing ---------------------------------------------------------------


def test_the_first_read_is_not_a_step():
    """A restored sensor value must not put the quest screen up on start."""
    eng = make()
    assert eng.note_quest(quest(), T0) is False
    assert eng.snapshot(T0, quest=quest())["questing"] is False


def test_a_stage_change_means_questing():
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    assert eng.note_quest(quest(stage=11), T0 + timedelta(seconds=30)) is True
    snapshot = eng.snapshot(T0 + timedelta(seconds=31), quest=quest(stage=11))
    assert snapshot["questing"] is True
    assert snapshot["quest"]["stage"] == 11


def test_questing_expires_with_the_session_window():
    eng = make(window_minutes=5)
    eng.note_quest(quest(stage=10), T0)
    eng.note_quest(quest(stage=11), T0 + timedelta(seconds=30))
    later = T0 + timedelta(minutes=6)
    assert eng.snapshot(later, quest=quest(stage=11))["questing"] is False


def test_a_finished_quest_is_never_questing():
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    done = quest(state="FINISHED", stage=99)
    eng.note_quest(done, T0 + timedelta(seconds=5))
    assert eng.snapshot(T0 + timedelta(seconds=6), quest=done)["questing"] is False


def test_the_same_reading_twice_is_not_a_step():
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    assert eng.note_quest(quest(stage=10), T0 + timedelta(seconds=5)) is False


def test_logging_out_ends_questing_too():
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    eng.note_quest(quest(stage=11), T0 + timedelta(seconds=5))
    eng.end()
    assert (
        eng.snapshot(T0 + timedelta(seconds=6), quest=quest(stage=11))["questing"]
        is False
    )


# -- completing -------------------------------------------------------------


def test_the_event_starts_a_celebration_and_it_ends_by_itself():
    eng = make()
    assert eng.mark_quest_complete("Dragon Slayer II", 300, T0) is True
    now = eng.snapshot(T0 + timedelta(seconds=1))
    assert now["celebrating"] is True
    assert now["quest_complete"]["quest"] == "Dragon Slayer II"
    assert now["quest_complete"]["lines"] == ["DRAGON SLAYER", "II"]
    assert now["quest_complete"]["points"] == 300

    later = eng.snapshot(T0 + timedelta(seconds=const.CELEBRATE_SECONDS + 1))
    assert later["celebrating"] is False
    # The name outlives the flag, for anything that wants it afterwards.
    assert later["quest_complete"]["quest"] == "Dragon Slayer II"
    assert later["quest_complete"]["seconds_ago"] == const.CELEBRATE_SECONDS + 1


def test_the_sensor_going_finished_is_a_completion_too():
    """For a plugin with the completion event switched off."""
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    eng.note_quest(
        quest(state="FINISHED", stage=99, points=300), T0 + timedelta(seconds=2)
    )
    snapshot = eng.snapshot(T0 + timedelta(seconds=3))
    assert snapshot["celebrating"] is True
    assert snapshot["quest_complete"]["points"] == 300


def test_event_and_sensor_together_are_one_completion():
    eng = make()
    eng.note_quest(quest(stage=10), T0)
    assert eng.mark_quest_complete("Dragon Slayer II", 300, T0 + timedelta(seconds=1))
    # The sensor's FINISHED a moment later is the same completion.
    assert (
        eng.note_quest(
            quest(state="FINISHED", stage=99, points=300), T0 + timedelta(seconds=2)
        )
        is True
    )
    assert eng.completed_at == T0 + timedelta(seconds=1)
    assert (
        eng.mark_quest_complete("Dragon Slayer II", 300, T0 + timedelta(seconds=3))
        is False
    )


def test_a_quest_already_finished_on_first_read_is_not_celebrated():
    eng = make()
    done = quest(state="FINISHED", stage=99)
    eng.note_quest(done, T0)
    assert eng.snapshot(T0, quest=done)["celebrating"] is False


def test_a_second_quest_is_a_new_celebration():
    eng = make()
    eng.mark_quest_complete("Dragon Slayer II", 300, T0)
    assert eng.mark_quest_complete("Monkey Madness II", 304, T0 + timedelta(seconds=5))
    assert eng.snapshot(T0 + timedelta(seconds=6))["quest_complete"]["quest"] == (
        "Monkey Madness II"
    )
