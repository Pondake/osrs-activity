"""Cache the OSRS skill icons locally.

Fetched once, then read from disk. That matters for the Pixoo in particular:
the Divoom integration opens the file with PIL during a render, so anything
that waits on HTTP there can hang the render.

Taken from the wiki instead of drawn by hand, after a hand-pixelled pickaxe at
24px turned out to read as a hammer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import ICON_BOX, ICON_DIR, SKILLS

_LOGGER = logging.getLogger(__name__)

WIKI_API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = (
    "home-assistant-osrs-activity/1.0 "
    "(https://github.com/Pondake/osrs-activity)"
)
BLANK = "blank.png"


async def async_ensure_icons(hass: HomeAssistant) -> dict | None:
    """Fetch the icons on first setup, and never again after that.

    Runs on setup so the icons are there without anyone calling a service.
    Only when the folder is empty, because re-fetching two dozen files on every
    restart would hammer a volunteer-run wiki for nothing.
    """
    target = Path(hass.config.path("www")) / ICON_DIR
    if await hass.async_add_executor_job(_has_icons, target):
        return None
    _LOGGER.info("Fetching the OSRS skill icons, once")
    return await async_download_icons(hass)


def _has_icons(target: Path) -> bool:
    """True once there is more than just the transparent stand-in."""
    try:
        return any(
            path.name != BLANK for path in target.glob("*.png")
        )
    except OSError:
        return False


async def async_download_icons(
    hass: HomeAssistant, overwrite: bool = False
) -> dict:
    """Fetch every skill icon into <config>/www/osrs_activity/icons/."""
    target = Path(hass.config.path("www")) / ICON_DIR
    await hass.async_add_executor_job(_prepare, target)

    session = async_get_clientsession(hass)
    fetched, skipped, failed = 0, 0, []

    for skill in SKILLS:
        path = target / f"{skill}.png"
        if not overwrite and await hass.async_add_executor_job(path.exists):
            skipped += 1
            continue
        try:
            url = await _async_find_file(session, skill)
            if not url:
                failed.append(skill)
                continue
            async with session.get(url, timeout=20) as response:
                response.raise_for_status()
                blob = await response.read()
            await hass.async_add_executor_job(_normalise, blob, path)
            fetched += 1
        except Exception as err:  # one bad icon must not stop the rest
            _LOGGER.warning("Could not fetch the %s icon: %s", skill, err)
            failed.append(skill)

    _LOGGER.info(
        "Skill icons: %d fetched, %d already there, %s failed",
        fetched,
        skipped,
        failed or "none",
    )
    return {"fetched": fetched, "skipped": skipped, "failed": failed}


async def _async_find_file(session, skill: str) -> str | None:
    """The wiki names them "<Skill> icon.png" consistently.

    Asked for through imageinfo because the file URL contains a hash path that
    cannot be guessed.
    """
    params = {
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "url",
        "titles": f"File:{skill.capitalize()} icon.png",
        "format": "json",
        "redirects": "1",
    }
    async with session.get(
        WIKI_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=20
    ) as response:
        response.raise_for_status()
        data = await response.json()

    for page in data.get("query", {}).get("pages", {}).values():
        for info in page.get("imageinfo", []):
            if info.get("url"):
                return info["url"]
    return None


def _prepare(target: Path) -> None:
    """Make the directory and the transparent fallback.

    The fallback has to exist so a skill without an icon still resolves to a
    real file. PIL raises on a missing path and the Divoom integration only
    catches template and network errors, so that would take down the page.
    """
    from PIL import Image

    target.mkdir(parents=True, exist_ok=True)
    blank = target / BLANK
    if not blank.exists():
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(blank)


def _normalise(blob: bytes, path: Path) -> None:
    """Put the icon on a fixed canvas, right-aligned and vertically centred.

    The wiki serves these at whatever size they happen to be (18x22 up to
    25x25), and a position on a 64px panel is a fixed number -- so without a
    common width the right edge lands somewhere different for every skill.
    Normalising on download is the cheapest place to fix that: nothing has to
    measure anything at render time, and scaling (which would distort the
    narrow ones) is not needed.
    """
    import io

    from PIL import Image

    source = Image.open(io.BytesIO(blob)).convert("RGBA")
    canvas = Image.new("RGBA", (ICON_BOX, ICON_BOX), (0, 0, 0, 0))
    # Negative offsets in case an icon is ever wider than the canvas; then it
    # loses a little on the left instead of sitting crooked.
    canvas.paste(source, (ICON_BOX - source.width, (ICON_BOX - source.height) // 2))
    canvas.save(path)
