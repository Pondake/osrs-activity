"""Serve the dashboard card that ships with this integration.

A HACS repository has exactly one category, so a Lovelace card would normally
mean a second repository to publish, install and keep in step. It does not have
to: an integration can serve its own static file and tell the frontend to load
it, which puts the card in the card picker as soon as the integration is set up.

The URL carries the version, so a browser that cached the old file gets the new
one after an update instead of a card that quietly does not match its data.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD = "osrs-activity-card.js"
SOURCE_DIR = Path(__file__).parent / "www"
URL_BASE = f"/{DOMAIN}"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and add it to the frontend, once per Home Assistant run."""
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    source = SOURCE_DIR / CARD
    if not await hass.async_add_executor_job(source.is_file):
        _LOGGER.warning("Card %s is missing; skipping registration", CARD)
        return

    # The manifest version, not the config-entry schema version: this is here
    # to bust a browser cache when the card changes, and the card changes with
    # releases.
    integration = await async_get_integration(hass, DOMAIN)

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(SOURCE_DIR), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{URL_BASE}/{CARD}?v={integration.version}")
    hass.data[f"{DOMAIN}_card_registered"] = True
    _LOGGER.debug("Registered the OSRS Activity card at %s", URL_BASE)
