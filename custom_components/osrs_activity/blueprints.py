"""Put the shipped blueprint where Home Assistant will find it.

HACS downloads only `custom_components/<domain>/` for an integration, so a
blueprint sitting anywhere else in the repository never reaches the user's
disk. It travels inside the component instead, and gets copied into the
blueprint folder on setup.

Copying it means it is in the blueprint list after setup, instead of the user
having to paste a raw GitHub URL into the import dialog.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SOURCE_DIR = Path(__file__).parent / "blueprints"


async def async_install_blueprints(hass: HomeAssistant) -> list[str]:
    """Copy any blueprint this integration ships, once.

    Never overwrites an existing file: an update would otherwise silently
    discard any edit the user had made to it.
    """
    return await hass.async_add_executor_job(_install, hass.config.path())


def _install(config_dir: str) -> list[str]:
    installed: list[str] = []
    if not SOURCE_DIR.is_dir():
        return installed

    for source in SOURCE_DIR.rglob("*.yaml"):
        # blueprints/<domain>/... mirrors the layout Home Assistant expects,
        # under a folder named after this integration so it is obvious where
        # the file came from and safe to delete.
        relative = source.relative_to(SOURCE_DIR)
        target = (
            Path(config_dir) / "blueprints" / relative.parent / DOMAIN / source.name
        )
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError as err:
            _LOGGER.warning("Could not install blueprint %s: %s", source.name, err)
            continue
        installed.append(str(target))
        _LOGGER.info("Installed blueprint %s", target)

    return installed
