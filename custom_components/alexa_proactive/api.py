"""OAuth2 client for Amazon LWA."""
from __future__ import annotations

import logging
import time

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import LWA_AUTH_URL, LWA_TOKEN_URL, SCOPE_PROACTIVE, SCOPE_SMAPI

_LOGGER = logging.getLogger(__name__)

_TOKEN_BUFFER_SECONDS = 60
_SMAPI_SCOPE_PARTS = frozenset(SCOPE_SMAPI.split())


class LWAClient:
    """Manages LWA access tokens for SMAPI and Proactive Events."""

    def __init__(self, hass: HomeAssistant, client_id: str, client_secret: str) -> None:
        self._hass = hass
        self._client_id = client_id
        self._client_secret = client_secret
        self._skill_client_id: str | None = None
        self._skill_client_secret: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._tokens: dict[str, _TokenCache] = {}
        self._refresh_tokens: dict[str, str] = {}

    def set_refresh_token(self, scope: str, refresh_token: str) -> None:
        self._refresh_tokens[scope] = refresh_token

    def set_skill_credentials(self, client_id: str, client_secret: str) -> None:
        self._skill_client_id = client_id
        self._skill_client_secret = client_secret

    def invalidate_token(self, scope: str) -> None:
        self._tokens.pop(scope, None)

    def get_refresh_token(self, scope: str) -> str | None:
        return self._refresh_tokens.get(scope)

    def get_authorization_url(self, redirect_uri: str, scope: str) -> str:
        from urllib.parse import quote, urlencode
        params = {
            "client_id": self._client_id,
            "scope": scope,
            "response_type": "code",
            "redirect_uri": redirect_uri,
        }
        return f"{LWA_AUTH_URL}?{urlencode(params, quote_via=quote)}"

    async def async_exchange_code(self, code: str, redirect_uri: str, scope: str) -> dict:
        """Exchange an authorization code for tokens."""
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": redirect_uri,
        }
        data = await self._async_token_request(payload, "code exchange")
        self._store_token(scope, data)
        return data

    async def async_get_proactive_token(self) -> str:
        """Return a valid token for the Proactive Events API.

        Uses client_credentials grant with skill-specific credentials.
        """
        if self._skill_client_id is None:
            raise HomeAssistantError("Skill credentials not configured — reconfigure the integration")
        cached = self._tokens.get(SCOPE_PROACTIVE)
        if cached and time.monotonic() < cached.expires_at:
            return cached.token

        payload = {
            "grant_type": "client_credentials",
            "client_id": self._skill_client_id,
            "client_secret": self._skill_client_secret,
            "scope": SCOPE_PROACTIVE,
        }
        data = await self._async_token_request(payload, "proactive client_credentials")
        self._store_token(SCOPE_PROACTIVE, data)
        return data["access_token"]

    async def async_get_smapi_token(self) -> str:
        """Return a valid SMAPI token (refresh token or cached)."""
        return await self._async_get_token(SCOPE_SMAPI)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def _async_get_token(self, scope: str) -> str:
        cached = self._tokens.get(scope)
        if cached and time.monotonic() < cached.expires_at:
            return cached.token

        refresh_token = self._refresh_tokens.get(scope)
        if refresh_token:
            await self._async_refresh(scope, refresh_token)
            cached = self._tokens.get(scope)
            if cached:
                return cached.token

        raise HomeAssistantError(f"No token for scope {scope} — reconfigure the integration")

    async def _async_refresh(self, scope: str, refresh_token: str) -> None:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        data = await self._async_token_request(payload, "refresh")
        self._store_token(scope, data)

    async def _async_token_request(self, payload: dict, label: str) -> dict:
        """Send a token request to LWA and return parsed JSON."""
        session = await self._get_session()
        try:
            async with session.post(LWA_TOKEN_URL, data=payload) as resp:
                data = await resp.json()
        except (aiohttp.ClientError, OSError) as err:
            raise HomeAssistantError(f"Cannot connect to Amazon LWA: {err}") from err

        error = data.get("error")
        if error:
            _LOGGER.error("LWA %s failed: %s — %s", label, error, data.get("error_description", ""))
            raise HomeAssistantError(f"LWA error: {error} — {data.get('error_description', '')}")

        if "access_token" not in data:
            raise HomeAssistantError("Invalid LWA token response")

        return data

    def _store_token(self, scope: str, data: dict) -> None:
        entry = _TokenCache(
            token=data["access_token"],
            expires_at=time.monotonic() + int(data.get("expires_in", 3600)) - _TOKEN_BUFFER_SECONDS,
        )
        self._tokens[scope] = entry
        if "refresh_token" in data:
            self._refresh_tokens[scope] = data["refresh_token"]
        scope_parts = scope.split()
        for part in scope_parts:
            if part != scope:
                self._tokens[part] = entry
                if "refresh_token" in data:
                    self._refresh_tokens[part] = data["refresh_token"]
        if _SMAPI_SCOPE_PARTS.issubset(scope_parts):
            self._tokens[SCOPE_SMAPI] = entry
            if "refresh_token" in data:
                self._refresh_tokens[SCOPE_SMAPI] = data["refresh_token"]


class _TokenCache:
    __slots__ = ("token", "expires_at")

    def __init__(self, token: str, expires_at: float) -> None:
        self.token = token
        self.expires_at = expires_at
