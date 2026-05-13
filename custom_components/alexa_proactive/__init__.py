"""The Alexa Proactive Events integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .api import LWAClient
from .const import CONF_ALEXA_USER_ID, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_COUNT, CONF_REGION, CONF_REFRESH_TOKEN, CONF_SENDER, CONF_SKILL_CLIENT_ID, CONF_SKILL_CLIENT_SECRET, DEFAULT_COUNT, DEFAULT_REGION, DEFAULT_SENDER, DOMAIN, SCOPE_SMAPI, SERVICE_SEND
from .proactive import ProactiveClient
from .views import AlexaProactiveView

_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SENDER, default=DEFAULT_SENDER): str,
        vol.Optional(CONF_COUNT, default=DEFAULT_COUNT): vol.All(int, vol.Range(min=1, max=99)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the alexa_proactive.send service."""

    async def _handle_send(call: ServiceCall) -> None:
        sender = call.data.get(CONF_SENDER, DEFAULT_SENDER)
        count = call.data.get(CONF_COUNT, DEFAULT_COUNT)

        entries = hass.config_entries.async_entries(DOMAIN)
        entry = next((e for e in entries if e.state == ConfigEntryState.LOADED), None)
        if entry is None:
            raise ServiceValidationError("Alexa Proactive Events integration is not configured")

        client: ProactiveClient | None = entry.runtime_data
        if client is None:
            raise ServiceValidationError("Integration not fully initialized")

        user_id = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get(CONF_ALEXA_USER_ID)
        await client.async_send(sender=sender, count=count, user_id=user_id)

    hass.services.async_register(DOMAIN, SERVICE_SEND, _handle_send, schema=_SERVICE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alexa Proactive Events from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}

    lwa_client = LWAClient(hass, entry.data[CONF_CLIENT_ID], entry.data[CONF_CLIENT_SECRET])
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    if refresh_token:
        lwa_client.set_refresh_token(SCOPE_SMAPI, refresh_token)

    skill_cid = entry.data.get(CONF_SKILL_CLIENT_ID)
    skill_csecret = entry.data.get(CONF_SKILL_CLIENT_SECRET)
    if skill_cid and skill_csecret:
        lwa_client.set_skill_credentials(skill_cid, skill_csecret)

    proactive_client = ProactiveClient(hass, lwa_client, entry.data.get(CONF_REGION, DEFAULT_REGION))
    entry.runtime_data = proactive_client

    hass.http.register_view(AlexaProactiveView(hass))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Alexa Proactive Events config entry."""
    entry.runtime_data = None

    entries = hass.data.get(DOMAIN)
    if entries is not None:
        entries.pop(entry.entry_id, None)
        if not entries:
            hass.data.pop(DOMAIN, None)
    return True
