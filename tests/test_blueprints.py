"""Tests for the blueprint installer.

The interesting part is when it may replace a file and when it may not, which
is easy to get subtly wrong in a way nobody notices until an update eats
someone's edits.

blueprints.py imports Home Assistant, which is not a test dependency here, so
those modules are stubbed just enough to import the file. Only _install is
exercised and it touches neither.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "osrs_activity"


def _stub(name: str, **attrs) -> None:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


def _load():
    for name in ("homeassistant", "homeassistant.core", "homeassistant.helpers"):
        sys.modules.setdefault(name, types.ModuleType(name))
    _stub("homeassistant.core", HomeAssistant=object)
    _stub("homeassistant.helpers.storage", Store=object)

    package = types.ModuleType("_oab")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_oab"] = package
    for name in ("const", "blueprints"):
        spec = importlib.util.spec_from_file_location(
            f"_oab.{name}", COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_oab.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["_oab.blueprints"]


blueprints = _load()


@pytest.fixture
def shipped(tmp_path, monkeypatch):
    """Point the installer at a throwaway source directory."""
    source = tmp_path / "shipped" / "automation"
    source.mkdir(parents=True)
    monkeypatch.setattr(blueprints, "SOURCE_DIR", tmp_path / "shipped")
    return source / "osrs_pixoo64.yaml"


def target_for(config_dir: Path) -> Path:
    return (
        config_dir / "blueprints" / "automation" / "osrs_activity" / "osrs_pixoo64.yaml"
    )


def test_installs_when_missing(tmp_path, shipped):
    shipped.write_text("first", encoding="utf-8")
    known: dict = {}
    written, changed = blueprints._install(str(tmp_path), known)

    assert len(written) == 1
    assert changed is True
    assert target_for(tmp_path).read_text(encoding="utf-8") == "first"
    assert known


def test_updates_a_copy_nobody_touched(tmp_path, shipped):
    shipped.write_text("first", encoding="utf-8")
    known: dict = {}
    blueprints._install(str(tmp_path), known)

    shipped.write_text("second", encoding="utf-8")
    written, changed = blueprints._install(str(tmp_path), known)

    assert len(written) == 1
    assert changed is True
    assert target_for(tmp_path).read_text(encoding="utf-8") == "second"


def test_leaves_an_edited_copy_alone(tmp_path, shipped):
    shipped.write_text("first", encoding="utf-8")
    known: dict = {}
    blueprints._install(str(tmp_path), known)

    target_for(tmp_path).write_text("mine, hands off", encoding="utf-8")
    shipped.write_text("second", encoding="utf-8")
    written, _changed = blueprints._install(str(tmp_path), known)

    assert written == []
    assert target_for(tmp_path).read_text(encoding="utf-8") == "mine, hands off"


def test_leaves_a_file_it_did_not_install(tmp_path, shipped):
    """Someone imported the blueprint by hand before ever installing this."""
    shipped.write_text("first", encoding="utf-8")
    target = target_for(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text("imported by hand", encoding="utf-8")

    written, _changed = blueprints._install(str(tmp_path), {})

    assert written == []
    assert target.read_text(encoding="utf-8") == "imported by hand"


def test_a_second_run_changes_nothing(tmp_path, shipped):
    shipped.write_text("first", encoding="utf-8")
    known: dict = {}
    blueprints._install(str(tmp_path), known)
    written, changed = blueprints._install(str(tmp_path), known)

    assert written == []
    assert changed is False
