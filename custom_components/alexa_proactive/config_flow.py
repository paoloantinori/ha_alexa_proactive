"""Config flow for Alexa Proactive Events."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import LWAClient
from .const import (
    CONF_INVOCATION_NAME,
    CONF_LOCALES,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SKILL_CLIENT_ID,
    CONF_SKILL_CLIENT_SECRET,
    CONF_SKILL_ID,
    CONF_VENDOR_ID,
    CONF_WEBHOOK_URL,
    COUNTRY_LOCALE_MAP,
    DEFAULT_INVOCATION_NAME,
    DEFAULT_LOCALE,
    DEFAULT_REGION,
    DOMAIN,
    LANGUAGE_LOCALE_MAP,
    LOCALE_LABELS,
    SCOPE_SMAPI,
)
from .models import get_default_invocation, get_model, normalize_invocation_name, validate_invocation_name
from .smapi import SMTPClient

_LOGGER = logging.getLogger(__name__)

_REGION_OPTIONS = [
    SelectOptionDict(value="na", label="North America"),
    SelectOptionDict(value="eu", label="Europe"),
    SelectOptionDict(value="fe", label="Far East"),
]

_LOCALE_OPTIONS = [
    SelectOptionDict(value=code, label=label)
    for code, label in LOCALE_LABELS.items()
]



class AlexaProactiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._region: str | None = None
        self._invocation_name: str = DEFAULT_INVOCATION_NAME
        self._selected_locales: list[str] = []
        self._setup_result: dict | None = None
        self._skill_creds: dict | None = None
        self._lwa_client: LWAClient | None = None

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        self._ensure_callback_view()
        if user_input:
            invocation_name = normalize_invocation_name(user_input[CONF_INVOCATION_NAME])
            if not validate_invocation_name(invocation_name):
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors={CONF_INVOCATION_NAME: "invalid_invocation_name"},
                )

            self._client_id = user_input[CONF_CLIENT_ID].strip()
            self._client_secret = user_input[CONF_CLIENT_SECRET].strip()
            self._region = user_input[CONF_REGION]
            self._invocation_name = invocation_name
            self._selected_locales = user_input.get(CONF_LOCALES, self._get_suggested_locales())

            await self.async_set_unique_id(self._client_id)
            self._abort_if_unique_id_configured()

            self._lwa_client = LWAClient(self.hass, self._client_id, self._client_secret)
            return await self.async_step_auth_smapi()

        return self.async_show_form(step_id="user", data_schema=self._user_schema(), errors=errors)

    def _user_schema(self) -> vol.Schema:
        suggested_locales = self._get_suggested_locales()
        default_invocation = get_default_invocation(suggested_locales[0]) if suggested_locales else DEFAULT_INVOCATION_NAME

        return vol.Schema({
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_CLIENT_SECRET): str,
            vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
                SelectSelectorConfig(options=_REGION_OPTIONS, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_INVOCATION_NAME, default=default_invocation): str,
            vol.Optional(CONF_LOCALES, default=suggested_locales): SelectSelector(
                SelectSelectorConfig(options=_LOCALE_OPTIONS, multiple=True, sort=True)
            ),
        })

    async def async_step_auth_smapi(self, user_input: dict | None = None):
        """Authorize with SMAPI scope via authorization code flow."""
        errors: dict[str, str] = {}
        if self._lwa_client is None:
            return await self.async_step_user()

        if user_input is not None:
            auth_codes = self.hass.data.get(DOMAIN, {}).get("auth_codes", {})
            lookup_key = f"{self.flow_id}_smapi"
            _LOGGER.info("Looking for auth code: key=%s, available_keys=%s", lookup_key, list(auth_codes.keys()))
            code = auth_codes.pop(lookup_key, None)
            if code:
                try:
                    redirect_uri = self._get_callback_url()
                    await self._lwa_client.async_exchange_code(code, redirect_uri, SCOPE_SMAPI)
                    return await self.async_step_setup()
                except HomeAssistantError as err:
                    _LOGGER.warning("SMAPI code exchange failed: %s", err)
                    errors["base"] = "invalid_auth"
            else:
                errors["base"] = "authorization_pending"

        redirect_uri = self._get_callback_url()
        auth_url = self._lwa_client.get_authorization_url(redirect_uri, SCOPE_SMAPI)
        auth_url += f"&state={self.flow_id}_smapi"

        return self.async_show_form(
            step_id="auth_smapi",
            errors=errors,
            description_placeholders={
                "auth_url": auth_url,
                "callback_url": redirect_uri,
            },
        )

    async def async_step_setup(self, _user_input: dict | None = None):
        webhook_url = await self._async_get_webhook_url()
        smapi_client = SMTPClient(self.hass, self._lwa_client)
        locales = self._selected_locales or [DEFAULT_LOCALE]

        try:
            models = {loc: get_model(loc, self._invocation_name) for loc in locales}
            self._setup_result = await smapi_client.async_setup_skill_complete(
                webhook_url=webhook_url, models=models, skill_name=self._invocation_name,
            )
            skill_id = self._setup_result["skill_id"]
            self._skill_creds = await smapi_client.async_get_skill_credentials(skill_id)
        except HomeAssistantError as err:
            _LOGGER.warning("SMAPI setup failed: %s", err)
            return self.async_show_form(step_id="setup", errors={"base": "smapi_error"})
        except Exception as err:
            _LOGGER.exception("Unexpected error during SMAPI setup: %s", err)
            return self.async_show_form(step_id="setup", errors={"base": "smapi_error"})

        self._build_timeout = not self._setup_result.get("build_succeeded", True)
        if self._build_timeout:
            _LOGGER.warning(
                "Skill %s created but model build timed out — showing warning to user",
                skill_id,
            )

        return await self.async_step_finish()

    async def async_step_finish(self, user_input: dict | None = None):
        if user_input is not None:
            refresh_token = self._lwa_client.get_refresh_token(SCOPE_SMAPI) or ""

            return self.async_create_entry(
                title="Alexa Proactive Events",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_REGION: self._region,
                    CONF_INVOCATION_NAME: self._invocation_name,
                    CONF_LOCALES: self._selected_locales,
                    CONF_SKILL_ID: self._setup_result["skill_id"],
                    CONF_VENDOR_ID: self._setup_result["vendor_id"],
                    CONF_WEBHOOK_URL: self._setup_result["webhook_url"],
                    CONF_REFRESH_TOKEN: refresh_token,
                    CONF_SKILL_CLIENT_ID: (self._skill_creds or {}).get("client_id"),
                    CONF_SKILL_CLIENT_SECRET: (self._skill_creds or {}).get("client_secret"),
                },
            )

        build_warning = ""
        if getattr(self, "_build_timeout", False):
            build_warning = (
                "⚠️ **The skill was created, but the interaction model build "
                "timed out.** It may still be building on Amazon's side. "
                "You can finish setup now, but if proactive notifications don't "
                "work, re-run setup or enable the skill manually in the "
                "[Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).\n\n"
            )
        return self.async_show_form(
            step_id="finish",
            description_placeholders={
                "invocation_name": self._invocation_name,
                "build_warning": build_warning,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AlexaProactiveOptionsFlow(config_entry)

    def _ensure_callback_view(self) -> None:
        if not self.hass.data.get(DOMAIN, {}).get("_callback_registered"):
            from .views import AlexaAuthCallbackView
            self.hass.http.register_view(AlexaAuthCallbackView(self.hass))
            self.hass.data.setdefault(DOMAIN, {})["_callback_registered"] = True

    def _get_base_url(self) -> str:
        try:
            from homeassistant.helpers.network import get_url
            return get_url(self.hass, allow_external=True, prefer_external=True)
        except Exception:
            return "http://localhost:8123"

    def _get_callback_url(self) -> str:
        return f"{self._get_base_url()}/auth/alexa_proactive/callback"

    async def _async_get_webhook_url(self) -> str:
        return f"{self._get_base_url()}/api/alexa_proactive"

    def _get_suggested_locales(self) -> list[str]:
        """Suggest locales based on HA's country/language config."""
        detected = None

        country = getattr(self.hass.config, "country", None)
        if country:
            detected = COUNTRY_LOCALE_MAP.get(country.upper())

        if not detected:
            language = getattr(self.hass.config, "language", None)
            if language:
                detected = LANGUAGE_LOCALE_MAP.get(language.split("-")[0].lower())

        if not detected:
            return [DEFAULT_LOCALE]

        if detected == DEFAULT_LOCALE:
            return [DEFAULT_LOCALE]

        return [detected, DEFAULT_LOCALE]


class AlexaProactiveOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            new_name = normalize_invocation_name(user_input[CONF_INVOCATION_NAME])
            old_name = normalize_invocation_name(
                self._config_entry.data.get(CONF_INVOCATION_NAME, DEFAULT_INVOCATION_NAME)
            )

            if not validate_invocation_name(new_name):
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema({
                        vol.Required(CONF_INVOCATION_NAME, default=user_input[CONF_INVOCATION_NAME]): str,
                    }),
                    errors={CONF_INVOCATION_NAME: "invalid_invocation_name"},
                )

            if new_name != old_name:
                try:
                    lwa_client = LWAClient(self.hass, self._config_entry.data[CONF_CLIENT_ID], self._config_entry.data[CONF_CLIENT_SECRET])
                    refresh_token = self._config_entry.data.get(CONF_REFRESH_TOKEN)
                    if refresh_token:
                        lwa_client.set_refresh_token(SCOPE_SMAPI, refresh_token)
                    smapi_client = SMTPClient(self.hass, lwa_client)
                    await smapi_client.async_update_manifest(
                        self._config_entry.data[CONF_SKILL_ID],
                        self._config_entry.data[CONF_WEBHOOK_URL],
                        new_name,
                    )
                    # The invocation name lives in the interaction model, so a
                    # manifest-only rename would never change what users say.
                    uploaded = await smapi_client.async_upload_models(
                        self._config_entry.data[CONF_SKILL_ID],
                        new_name,
                        self._config_entry.data.get(CONF_LOCALES, [DEFAULT_LOCALE]),
                    )
                    if not uploaded:
                        raise HomeAssistantError(
                            "Rename failed: no interaction model could be uploaded"
                        )
                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data={**self._config_entry.data, CONF_INVOCATION_NAME: new_name}
                    )
                except HomeAssistantError as err:
                    _LOGGER.warning("Failed to update skill name: %s", err)
                    errors["base"] = "smapi_error"

            if not errors:
                return self.async_create_entry(title="", data={CONF_INVOCATION_NAME: new_name})

        current_name = self._config_entry.data.get(CONF_INVOCATION_NAME, DEFAULT_INVOCATION_NAME)
        schema = vol.Schema({
            vol.Required(CONF_INVOCATION_NAME, default=current_name): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
