"""Config flow: pick a player, then two windows."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_FOCUS_SECONDS,
    CONF_USERNAME,
    CONF_WINDOW_MINUTES,
    DEFAULT_FOCUS_SECONDS,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    RUNELITE_DOMAIN,
)
from .coordinator import sanitize


def _options_schema(current: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_WINDOW_MINUTES,
                default=current.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=60, step=0.5, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_FOCUS_SECONDS,
                default=current.get(CONF_FOCUS_SECONDS, DEFAULT_FOCUS_SECONDS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5, max=300, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


class OsrsActivityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one player."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the RuneLite players that are not tracked yet.

        The usernames come from the RuneLite integration rather than a text
        box: a typo there would silently match no skill sensors at all, and the
        result would look like an integration that simply does not work.
        """
        known = {
            entry.data.get("username")
            for entry in self.hass.config_entries.async_entries(RUNELITE_DOMAIN)
            if entry.data.get("username")
        }
        if not known:
            return self.async_abort(reason="no_runelite")

        taken = {
            entry.data.get(CONF_USERNAME)
            for entry in self._async_current_entries()
        }
        available = sorted(known - taken)
        if not available:
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            await self.async_set_unique_id(sanitize(username))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=username,
                data={CONF_USERNAME: username},
                options={
                    CONF_WINDOW_MINUTES: user_input[CONF_WINDOW_MINUTES],
                    CONF_FOCUS_SECONDS: user_input[CONF_FOCUS_SECONDS],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): SelectSelector(
                    SelectSelectorConfig(
                        options=available, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        ).extend(_options_schema({}).schema)
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OsrsActivityOptionsFlow:
        return OsrsActivityOptionsFlow()


class OsrsActivityOptionsFlow(OptionsFlow):
    """Change the two windows afterwards."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(dict(self.config_entry.options)),
        )
