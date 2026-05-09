"""OAuth2 client for Amazon Login with Amazon (LWA) token management."""

from __future__ import annotations

import time

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import LWA_TOKEN_URL, SCOPE_PROACTIVE, SCOPE_SMAPI

_TOKEN_BUFFER_SECONDS = 60

_CREDENTIAL_ERRORS = {400, 401}


class LWAClient:
    """Manages LWA access tokens with caching per scope."""

    def __init__(self, hass: HomeAssistant, client_id: str, client_secret: str) -> None:
        self._hass = hass
        self._client_id = client_id
        self._client_secret = client_secret
        self._session: aiohttp.ClientSession | None = None
        self._tokens: dict[str, dict[str, float | str]] = {}

    async def async_get_proactive_token(self) -> str:
        """Return a valid access token for the proactive events scope."""
        return await self._async_get_token(SCOPE_PROACTIVE)

    async def async_get_smapi_token(self) -> str:
        """Return a valid access token for the SMAPI scope."""
        return await self._async_get_token(SCOPE_SMAPI)

    async def _async_get_token(self, scope: str) -> str:
        """Return a cached token if still valid, otherwise fetch a new one."""
        cached = self._tokens.get(scope)
        if cached and time.monotonic() < cached["expires_at"]:
            return cached["access_token"]

        token_data = await self._async_request_token(scope)
        self._tokens[scope] = {
            "access_token": token_data["access_token"],
            "expires_at": time.monotonic() + token_data["expires_in"] - _TOKEN_BUFFER_SECONDS,
        }
        return token_data["access_token"]

    async def _async_request_token(self, scope: str) -> dict:
        """Request a new access token from LWA for the given scope."""
        if self._session is None or self._session.closed:
            self._session = async_create_clientsession(self._hass)

        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": scope,
        }

        try:
            async with self._session.post(LWA_TOKEN_URL, data=payload) as resp:
                if resp.status in _CREDENTIAL_ERRORS:
                    raise HomeAssistantError("Invalid LWA credentials")
                resp.raise_for_status()
                data = await resp.json()
        except HomeAssistantError:
            raise
        except aiohttp.ClientError:
            raise HomeAssistantError("Cannot connect to Amazon LWA")

        if "access_token" not in data:
            raise HomeAssistantError("Missing required scope")

        return data
