"""OSRS Activity: what a RuneLite player is doing right now."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_FOCUS_SECONDS,
    CONF_USERNAME,
    CONF_WINDOW_MINUTES,
    DEFAULT_FOCUS_SECONDS,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
)
from .coordinator import ActivityCoordinator
from .icons import async_download_icons

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

SERVICE_DOWNLOAD_ICONS = "download_skill_icons"
DOWNLOAD_ICONS_SCHEMA = vol.Schema(
    {vol.Optional("overwrite", default=False): cv.boolean}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one player."""
    coordinator = ActivityCoordinator(
        hass,
        entry_id=entry.entry_id,
        username=entry.data[CONF_USERNAME],
        window_minutes=entry.options.get(
            CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
        ),
        focus_seconds=entry.options.get(
            CONF_FOCUS_SECONDS, DEFAULT_FOCUS_SECONDS
        ),
    )
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear one player down."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: ActivityCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed. Both windows are read at construction, so start over."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register the shared services, once, on the first entry."""
    if hass.services.has_service(DOMAIN, SERVICE_DOWNLOAD_ICONS):
        return

    async def _handle_download(call: ServiceCall) -> dict:
        result = await async_download_icons(
            hass, overwrite=call.data.get("overwrite", False)
        )
        for coordinator in hass.data.get(DOMAIN, {}).values():
            await coordinator.async_refresh_icons()
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_ICONS,
        _handle_download,
        schema=DOWNLOAD_ICONS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
