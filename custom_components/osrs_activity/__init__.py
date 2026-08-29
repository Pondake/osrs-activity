"""OSRS Activity: what a RuneLite player is doing right now."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .blueprints import async_install_blueprints
from .const import (
    CONF_FOCUS_SECONDS,
    CONF_USERNAME,
    CONF_WINDOW_MINUTES,
    DEFAULT_FOCUS_SECONDS,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
)
from .coordinator import ActivityCoordinator
from .frontend import async_register_card
from .icons import async_download_icons, async_ensure_icons

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
    await async_register_card(hass)
    # Both of these make the integration work out of the box rather than after
    # reading the readme, and neither is allowed to hold setup up or fail it:
    # no network, no write permission, still a working integration.
    entry.async_create_background_task(
        hass, _async_first_run(hass, coordinator), f"{DOMAIN}_first_run"
    )
    return True


async def _async_first_run(
    hass: HomeAssistant, coordinator: ActivityCoordinator
) -> None:
    """Fetch the skill icons and install the blueprint, once, in the background."""
    try:
        await async_install_blueprints(hass)
    except Exception:  # a missing blueprint must not be a failed setup
        _LOGGER.exception("Could not install the bundled blueprint")

    try:
        if await async_ensure_icons(hass):
            await coordinator.async_refresh_icons()
    except Exception:  # the service can always be run by hand
        _LOGGER.exception(
            "Could not fetch the skill icons; run %s.%s to retry",
            DOMAIN,
            SERVICE_DOWNLOAD_ICONS,
        )


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
