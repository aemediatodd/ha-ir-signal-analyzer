"""Config flow for IR Signal Analyzer."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_SOURCE, DEFAULT_NAME, DOMAIN


class IRSignalAnalyzerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            source = str(user_input.get(CONF_SOURCE, "")).strip()
            unique_id = source.casefold() if source else "all_sources"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            title = f"{DEFAULT_NAME} ({source})" if source else DEFAULT_NAME
            return self.async_create_entry(title=title, data={CONF_SOURCE: source})

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOURCE, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

