"""Config flow for Alexa Proactive Events."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode
from homeassistant.helpers.network import get_url

from .api import LWAClient
from .const import CONF_REGION, CONF_WEBHOOK_ID, DEFAULT_REGION, DOMAIN
from .models import MODELS
from .smapi import SMTPClient

_REGION_OPTIONS = [
    SelectOptionDict(value="na", label="North America"),
    SelectOptionDict(value="eu", label="Europe"),
    SelectOptionDict(value="fe", label="Far East"),
]

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
            SelectSelectorConfig(options=_REGION_OPTIONS, mode=SelectSelectorMode.DROPDOWN)
        ),
    }
)


class AlexaProactiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._region: str | None = None
        self._setup_result: dict | None = None

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input:
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]
            self._region = user_input[CONF_REGION]

            error = await self._async_validate_credentials()
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(self._client_id)
                self._abort_if_unique_id_configured()
                return await self.async_step_setup()

        return self.async_show_form(step_id="user", data_schema=_USER_SCHEMA, errors=errors)

    async def async_step_setup(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is None:
            webhook_url = await self._async_get_webhook_url()
            lwa_client = LWAClient(self.hass, self._client_id, self._client_secret)
            smapi_client = SMTPClient(self.hass, lwa_client)

            try:
                self._setup_result = await smapi_client.async_setup_skill_complete(
                    webhook_url=webhook_url, models=MODELS,
                )
            except HomeAssistantError:
                errors["base"] = "smapi_error"
                return self.async_show_form(step_id="setup", errors=errors)

            return await self.async_step_finish()

        return self.async_show_form(step_id="setup", errors=errors)

    async def async_step_finish(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="Alexa Proactive Events",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_REGION: self._region,
                    "skill_id": self._setup_result["skill_id"],
                    "vendor_id": self._setup_result["vendor_id"],
                    "webhook_url": self._setup_result["webhook_url"],
                },
            )

        return self.async_show_form(step_id="finish")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AlexaProactiveOptionsFlow(config_entry)

    async def _async_validate_credentials(self) -> str | None:
        lwa_client = LWAClient(self.hass, self._client_id, self._client_secret)
        try:
            await lwa_client.async_get_proactive_token()
        except HomeAssistantError:
            return "invalid_auth"
        try:
            await lwa_client.async_get_smapi_token()
        except HomeAssistantError:
            return "scope_missing"
        return None

    async def _async_get_webhook_url(self) -> str:
        base_url = get_url(self.hass, require_external=True)
        return f"{base_url}/api/alexa_proactive"


class AlexaProactiveOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init")
