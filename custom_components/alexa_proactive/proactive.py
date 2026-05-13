"""Proactive Events API client for sending Alexa notifications."""
from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta, timezone

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import LWAClient
from .const import DEFAULT_SENDER, EVENT_SCHEMA, PROACTIVE_API_URLS, SCOPE_PROACTIVE

_LOGGER = logging.getLogger(__name__)

_EXPIRY_HOURS = 1


class ProactiveClient:
    """Sends proactive notification events to the Alexa Proactive Events API."""

    def __init__(self, hass: HomeAssistant, lwa_client: LWAClient, region: str) -> None:
        self._hass = hass
        self._lwa = lwa_client
        self._region = region
        self._session: aiohttp.ClientSession | None = None

    async def async_send(
        self,
        sender: str = DEFAULT_SENDER,
        count: int = 1,
        user_id: str | None = None,
    ) -> dict:
        """Send a proactive notification event.

        If user_id is provided, sends a unicast notification to that user.
        Otherwise sends a multicast notification to all subscribed users.
        """
        token = await self._lwa.async_get_proactive_token()
        payload = self._build_payload(sender, count, user_id)

        try:
            return await self._async_post(token, payload)
        except HomeAssistantError:
            _LOGGER.debug("Retrying with fresh token")
            self._lwa.invalidate_token(SCOPE_PROACTIVE)
            token = await self._lwa.async_get_proactive_token()
            return await self._async_post(token, payload)

    def _build_payload(self, sender: str, count: int, user_id: str | None) -> dict:
        """Build the proactive event JSON payload."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=_EXPIRY_HOURS)
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

        audience = (
            {"type": "Unicast", "payload": {"user": user_id}}
            if user_id
            else {"type": "Multicast", "payload": {}}
        )

        return {
            "timestamp": now.isoformat(),
            "referenceId": f"pingme-{int(now.timestamp())}-{suffix}",
            "expiryTime": expires.isoformat(),
            "event": {
                "name": EVENT_SCHEMA,
                "payload": {
                    "state": {"status": "UNREAD", "freshness": "NEW"},
                    "messageGroup": {
                        "count": count,
                        "creator": {"name": sender},
                    },
                },
            },
            "relevantAudience": audience,
        }

    def _api_url(self) -> str:
        hostname = PROACTIVE_API_URLS.get(self._region, PROACTIVE_API_URLS["na"])
        return f"https://{hostname}/v1/proactiveEvents/stages/development"

    async def _async_post(self, token: str, payload: dict) -> dict:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
            self._session = aiohttp.ClientSession(connector=connector)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        url = self._api_url()
        _LOGGER.debug("Proactive Events POST %s — token prefix: %s", url, token[:20])
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 403:
                    body = await resp.text()
                    _LOGGER.error("Proactive Events API 403: %s", body)
                    raise HomeAssistantError("Proactive Events API returned 403 — token may be expired")
                if resp.status == 400:
                    body = await resp.text()
                    _LOGGER.error("Bad proactive event payload: %s", body)
                    raise HomeAssistantError(f"Invalid proactive event payload: {body[:200]}")
                resp.raise_for_status()
                return await resp.json() if await resp.text() else {}
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Cannot connect to Proactive Events API: {err}") from err
