"""Tests for the publish guard.

These plant one of each kind of finding and check it gets caught, and check
that things which legitimately appear in this repo do not. Without them a
broken rule would still report "clean" and nobody would notice.

The fixtures below include a fake API key and a fake JWT, so this file is
allowlisted by path in .gitleaks.toml. gitleaks flags them correctly; they have
to stay for the tests to mean anything.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "scan_leaks", ROOT / "tools" / "scan_leaks.py"
)
scan_leaks = importlib.util.module_from_spec(spec)
sys.modules["scan_leaks"] = scan_leaks
spec.loader.exec_module(scan_leaks)


def findings(tmp_path: Path, text: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text(text, encoding="utf-8")
    return [label for _line, label, _hit in scan_leaks.scan(path)]


CAUGHT = [
    ("private IP address", 'PIXOO = "192.168.142.36"'),
    ("private IP address", 'HOST = "10.0.0.14"'),
    ("email address", "# contact: someone@example.com"),
    ("token that looks like a JWT", "token = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0"),
    ("private key block", "-----BEGIN RSA PRIVATE KEY-----"),
    ("credential assignment", 'api_key = "abcdef0123456789abcdef"'),
    ("path on someone's own disk", r'OUT = "I:\\home-assistant\\docs"'),
    ("path on someone's own disk", 'OUT = "C:/Users/someone/thing"'),
    ("absolute Home Assistant config path", 'ICONS = "/config/www/icons"'),
    ("AI attribution", "Co-authored-by: Claude <noreply@anthropic.com>"),
    ("name from a private setup", 'ENTITY = "sensor.kantoor_rl_skill_mining"'),
    ("name from a private setup", 'LIGHT = "light.divoom_pixoo_64_light"'),
]


def test_each_rule_catches_its_own_case(tmp_path):
    for label, line in CAUGHT:
        assert label in findings(tmp_path, line), f"missed: {line}"


CLEAN = [
    'DOCS = "https://github.com/Pondake/osrs-activity"',
    'WIKI = "https://oldschool.runescape.wiki/api.php"',
    "author = 4643209+Pondake@users.noreply.github.com",
    'target = hass.config.path("www")',
    "Run once; the icons land in config/www/osrs_activity/icons/.",
    'ICON_DIR = "osrs_activity/icons"',
    "for skill in SKILLS:",
    # Shaped like an address, is not one.
    'OUTPUTS = {"icon@2x.png": 512, "logo@2x.png": 512}',
]


def test_the_real_repo_content_is_not_flagged(tmp_path):
    for line in CLEAN:
        assert findings(tmp_path, line) == [], f"false positive: {line}"


def test_the_allow_marker_silences_a_line(tmp_path):
    line = 'HOST = "192.168.1.5"  # scan-leaks: allow'
    assert findings(tmp_path, line) == []


def test_binary_and_image_files_are_skipped(tmp_path):
    path = tmp_path / "icon.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n192.168.1.5")
    assert scan_leaks.scan(path) == []


def test_the_repo_itself_is_clean():
    """The guard, run against what it guards."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "tools/scan_leaks.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
