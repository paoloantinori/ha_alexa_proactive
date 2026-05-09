"""SMAPI client for automated Alexa skill management."""
from __future__ import annotations

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import LWAClient
from .const import EVENT_SCHEMA, SMAPI_BASE_URL


class SMTPClient:

    def __init__(self, hass: HomeAssistant, lwa_client: LWAClient) -> None:
        self._hass = hass
        self._lwa_client = lwa_client
        self._session: aiohttp.ClientSession | None = None

    async def async_get_vendor_id(self) -> str:
        data = await self._async_request("GET", "/v1/vendors")
        vendors = data.get("vendors", [])
        if not vendors:
            raise HomeAssistantError("No Amazon vendor account found")
        return vendors[0]["id"]

    async def async_create_skill(self, webhook_url: str, skill_name: str = "Home Assistant") -> str:
        vendor_id = await self.async_get_vendor_id()
        manifest = self._build_manifest(webhook_url, skill_name)
        data = await self._async_request("POST", "/v1/skills", json={"vendorId": vendor_id, "manifest": manifest})
        return data["skillId"]

    async def async_update_manifest(self, skill_id: str, webhook_url: str, skill_name: str = "Home Assistant") -> None:
        manifest = self._build_manifest(webhook_url, skill_name)
        await self._async_request("PUT", f"/v1/skills/{skill_id}/stages/development/manifest", json={"manifest": manifest})

    async def async_upload_model(self, skill_id: str, locale: str, model: dict) -> None:
        await self._async_request(
            "PUT",
            f"/v1/skills/{skill_id}/stages/development/interactionModel/locales/{locale}",
            json=model,
        )

    async def async_enable_skill(self, skill_id: str) -> None:
        await self._async_request("PUT", f"/v1/skills/{skill_id}/stages/development/enablement", json={})

    async def async_setup_skill_complete(
        self,
        webhook_url: str,
        models: dict[str, dict],
        skill_name: str = "Home Assistant",
    ) -> dict:
        """Orchestrate full skill setup: create, upload models, enable."""
        vendor_id = await self.async_get_vendor_id()
        skill_id: str | None = None

        try:
            skill_id = await self.async_create_skill(webhook_url, skill_name)
        except HomeAssistantError as err:
            if "409" in str(err):
                skill_id = await self._async_resolve_conflict(webhook_url, skill_name)
            else:
                raise

        for locale, model in models.items():
            await self.async_upload_model(skill_id, model=model, locale=locale)

        await self.async_enable_skill(skill_id)
        return {"skill_id": skill_id, "vendor_id": vendor_id, "webhook_url": webhook_url}

    async def _async_resolve_conflict(self, webhook_url: str, skill_name: str) -> str:
        vendor_id = await self.async_get_vendor_id()
        data = await self._async_request("GET", "/v1/skills", params={"vendorId": vendor_id})
        skills = data.get("skills", [])
        if not skills:
            raise HomeAssistantError("Skill conflict but no existing skills found")
        skill_id = skills[0]["skillId"]
        await self.async_update_manifest(skill_id, webhook_url, skill_name)
        return skill_id

    def _build_manifest(self, webhook_url: str, skill_name: str) -> dict:
        """Build the skill manifest payload."""
        return {
            "publishingInformation": {
                "locales": {
                    "en-US": {
                        "name": skill_name,
                        "summary": "Proactive notifications from Home Assistant.",
                        "description": "Receives proactive notification alerts from your Home Assistant instance.",
                        "examplePhrases": [f"Alexa, open {skill_name}"],
                        "keywords": ["notification", "home automation", "alert"],
                    },
                    "it-IT": {
                        "name": skill_name,
                        "summary": "Notifiche proattive da Home Assistant.",
                        "description": "Ricevi avvisi di notifica proattivi dalla tua istanza Home Assistant.",
                        "examplePhrases": [f"Alexa, apri {skill_name}"],
                        "keywords": ["notifica", "domotica", "avviso"],
                    },
                },
                "isAvailableWorldwide": True,
                "testingInstructions": f"Say 'Alexa, open {skill_name}'. Check for notification.",
            },
            "apis": {
                "custom": {
                    "endpoint": {
                        "sslCertificateType": "Trusted",
                        "uri": webhook_url,
                    },
                    "interfaces": [],
                }
            },
            "manifestVersion": "1.0",
            "permissions": [{"name": "alexa::devices:all:notifications:write"}],
            "events": {
                "publications": [{"eventName": EVENT_SCHEMA}],
                "subscriptions": [{"eventName": "SKILL_PROACTIVE_SUBSCRIPTION_CHANGED"}],
                "endpoint": {
                    "sslCertificateType": "Trusted",
                    "uri": webhook_url,
                },
                "regions": {
                    "NA": {"endpoint": {"sslCertificateType": "Trusted", "uri": webhook_url}},
                    "EU": {"endpoint": {"sslCertificateType": "Trusted", "uri": webhook_url}},
                    "FE": {"endpoint": {"sslCertificateType": "Trusted", "uri": webhook_url}},
                },
            },
        }

    async def _async_request(self, method: str, path: str, **kwargs) -> dict | None:
        token = await self._lwa_client.async_get_smapi_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        if self._session is None or self._session.closed:
            self._session = async_create_clientsession(self._hass)

        url = f"{SMAPI_BASE_URL}{path}"
        try:
            async with self._session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 401:
                    raise HomeAssistantError("Invalid LWA credentials")
                if resp.status == 409:
                    text = await resp.text()
                    raise HomeAssistantError(f"Conflict (409): {text}")
                if resp.status == 204:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"SMAPI request failed: {err}") from err
