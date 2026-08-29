"""Refuse to publish anything that belongs to one particular house.

This repo was carved out of a private Home Assistant config, so the risk is not
really API keys -- it is the ordinary detail that comes along for the ride: an
entity named after a room, a device name, a LAN address, a path off someone's
own disk. None of that is dangerous on its own and all of it is permanent once
it is on GitHub.

    python tools/scan_leaks.py            # everything git tracks
    python tools/scan_leaks.py --staged   # only what is about to be committed

Exits non-zero on a finding, so it works as a hook and as a CI gate. When a
match is genuinely fine, put `scan-leaks: allow` in a comment on that line.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A marker on the line itself, for the times a rule is right in general and
# wrong here. Deliberately noisy to type.
ALLOW_MARK = "scan-leaks: allow"

# Matches that are known-good wherever they appear.
ALWAYS_FINE = [
    re.compile(r"\d+\+\w+@users\.noreply\.github\.com"),
    re.compile(r"https?://(?:www\.)?github\.com/"),
    re.compile(r"oldschool\.runescape\.wiki"),
    # Retina asset naming. icon@2x.png has the shape of an address and is not
    # one; without this the email rule fires on every high-dpi image in the
    # repository.
    re.compile(r"@\d+x\.(?:png|jpg|jpeg|gif|svg|webp)$", re.IGNORECASE),
]

RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "private IP address",
        re.compile(
            r"\b(?:192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
        ),
    ),
    (
        "email address",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "token that looks like a JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|auth_token|"
            r"access_token|bearer)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_-]{16,}"
        ),
    ),
    (
        "path on someone's own disk",
        re.compile(r"(?i)\b[a-z]:[\\/]{1,2}(?:users|home-assistant|osrs|config)\b"),
    ),
    (
        "absolute Home Assistant config path",
        re.compile(r"(?<![\w>/])/config/"),  # scan-leaks: allow
    ),
    (
        "AI attribution",
        re.compile(
            r"(?i)co-authored-by:\s*(?:claude|copilot)"
            r"|generated with \[?(?:claude|chatgpt)"
            r"|anthropic\.com"
        ),
    ),
]

# The word list lives in a data file, not in here. Two reasons: it is edited
# far more often than this code, and a scanner that scans itself would flag
# every word it knows -- which is why that one file, and the test fixtures, are
# the only paths exempt below.
WORDS_FILE = Path(__file__).with_name("private_words.txt")
# Names that must be blocked but must NOT be published -- a company, a
# surname, a network name. Git ignores this one, so blocking a name never
# means publishing it.
LOCAL_WORDS_FILE = Path(__file__).with_name("private_words.local.txt")


def _private_words() -> list[str]:
    words = []
    for source in (WORDS_FILE, LOCAL_WORDS_FILE):
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(re.escape(line))
    return words


# A word boundary is no good here: an entity id looks like
# sensor.<room>_rl_skill_mining, and an underscore counts as a word
# character -- so the boundary never falls where it matters. Underscores
# have to read as separators instead.
RULES.append(
    (
        "name from a private setup",
        re.compile(
            rf"(?i)(?<![A-Za-z0-9])(?:{'|'.join(_private_words())})(?![A-Za-z0-9])"
        ),
    )
)

# Exempt by name, and only these. The word list IS the words; the test file's
# whole job is to hold one example of every finding. Anything else that matches
# has to say so on the line with `scan-leaks: allow`.
SELF_EXEMPT = {
    "tools/private_words.txt",
    "tools/private_words.local.txt",
    "tests/test_scan_leaks.py",
}

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pyc"}


def tracked_files(staged: bool) -> list[Path]:
    command = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
        if staged
        else ["git", "ls-files"]
    )
    output = subprocess.run(
        command, capture_output=True, text=True, check=True
    ).stdout
    return [Path(line) for line in output.splitlines() if line]


def scan(path: Path) -> list[tuple[int, str, str]]:
    if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARK in line:
            continue
        for label, pattern in RULES:
            match = pattern.search(line)
            if not match:
                continue
            hit = match.group(0)
            if any(fine.search(hit) for fine in ALWAYS_FINE):
                continue
            findings.append((number, label, hit))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="only scan what is staged, for use as a pre-commit hook",
    )
    args = parser.parse_args()

    total = 0
    for path in tracked_files(args.staged):
        if path.as_posix() in SELF_EXEMPT:
            continue
        for number, label, hit in scan(path):
            print(f"{path}:{number}: {label}: {hit}")
            total += 1

    if total:
        print(
            f"\n{total} finding(s). Fix them, or add `{ALLOW_MARK}` to the line "
            "if it is genuinely fine.",
            file=sys.stderr,
        )
        return 1

    print("scan_leaks: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
