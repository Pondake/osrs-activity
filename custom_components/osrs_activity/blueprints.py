"""Put the shipped blueprint where Home Assistant will find it, and keep it current.

HACS downloads only `custom_components/<domain>/` for an integration, so a
blueprint sitting anywhere else in the repository never reaches the user's
disk. It travels inside the component instead, and gets copied into the
blueprint folder on setup. It is an automation blueprint rather than a script
one, so creating it from the list is also switching it on; a script would have
needed an automation written by hand to call it.

Updating it is the awkward half. Overwriting every time discards edits somebody
made; never overwriting means a fix in a new release reaches nobody who already
had the old one. So the hash of what was installed is recorded, and the file is
replaced only while it still matches that. An edited blueprint is left alone,
and the log says so.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SOURCE_DIR = Path(__file__).parent / "blueprints"
STORE_KEY = f"{DOMAIN}.blueprints"
STORE_VERSION = 1


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def async_install_blueprints(hass: HomeAssistant) -> list[str]:
    """Install or refresh every blueprint this integration ships."""
    store: Store = Store(hass, STORE_VERSION, STORE_KEY)
    known = await store.async_load() or {}
    written, changed = await hass.async_add_executor_job(
        _install, hass.config.path(), known
    )
    if changed:
        await store.async_save(known)
    return written


def _install(config_dir: str, known: dict) -> tuple[list[str], bool]:
    """Returns the paths written, and whether the record needs saving."""
    written: list[str] = []
    changed = False
    if not SOURCE_DIR.is_dir():
        return written, changed

    for source in SOURCE_DIR.rglob("*.yaml"):
        # blueprints/<type>/<domain>/... mirrors the layout Home Assistant
        # expects, under a folder named after this integration so it is obvious
        # where the file came from and safe to delete.
        relative = source.relative_to(SOURCE_DIR)
        target = (
            Path(config_dir) / "blueprints" / relative.parent / DOMAIN / source.name
        )
        key = relative.as_posix()

        try:
            fresh = _digest(source)
            if target.exists():
                current = _digest(target)
                if current == fresh:
                    if known.get(key) != fresh:
                        known[key] = fresh
                        changed = True
                    continue
                if known.get(key) is None:
                    _LOGGER.info(
                        "Leaving %s alone: no record of installing it, so it "
                        "may not be ours to replace",
                        target,
                    )
                    continue
                if known[key] != current:
                    _LOGGER.info(
                        "Leaving %s alone: it has been edited since it was "
                        "installed, so this update does not touch it",
                        target,
                    )
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            known[key] = fresh
            changed = True
        except OSError as err:
            _LOGGER.warning("Could not install blueprint %s: %s", source.name, err)
            continue

        written.append(str(target))
        _LOGGER.info("Installed blueprint %s", target)

    return written, changed
