"""SMAPI client for automated Alexa skill management."""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import LWAClient
from .const import EVENT_SCHEMA, LOCALE_LABELS, SMAPI_BASE_URL

_LOGGER = logging.getLogger(__name__)

_EN_MANIFEST_INFO = {
    "summary": "Proactive notifications from Home Assistant.",
    "description": "Receives proactive notification alerts from your Home Assistant instance.",
    "keywords": ["notification", "home automation", "alert"],
}

_MANIFEST_LOCALE_INFO: dict[str, dict] = {
    "ar-SA": {
        "summary": "إشعارات استباقية من Home Assistant.",
        "description": "تلقي تنبيهات الإشعارات الاستباقية من مثيل Home Assistant الخاص بك.",
        "keywords": ["إشعار", "أتمتة منزلية", "تنبيه"],
    },
    "de-DE": {
        "summary": "Proaktive Benachrichtigungen von Home Assistant.",
        "description": "Empfängt proaktive Benachrichtigungsalarme von Ihrer Home Assistant-Instanz.",
        "keywords": ["Benachrichtigung", "Hausautomation", "Alarm"],
    },
    "en-AU": _EN_MANIFEST_INFO,
    "en-CA": _EN_MANIFEST_INFO,
    "en-GB": _EN_MANIFEST_INFO,
    "en-IN": _EN_MANIFEST_INFO,
    "en-US": _EN_MANIFEST_INFO,
    "es-ES": {
        "summary": "Notificaciones proactivas de Home Assistant.",
        "description": "Recibe alertas de notificación proactiva de tu instancia de Home Assistant.",
        "keywords": ["notificación", "domótica", "alerta"],
    },
    "es-MX": {
        "summary": "Notificaciones proactivas de Home Assistant.",
        "description": "Recibe alertas de notificación proactiva de tu instancia de Home Assistant.",
        "keywords": ["notificación", "domótica", "alerta"],
    },
    "es-US": {
        "summary": "Notificaciones proactivas de Home Assistant.",
        "description": "Recibe alertas de notificación proactiva de tu instancia de Home Assistant.",
        "keywords": ["notificación", "domótica", "alerta"],
    },
    "fr-CA": {
        "summary": "Notifications proactives de Home Assistant.",
        "description": "Reçoit des alertes de notification proactive de votre instance Home Assistant.",
        "keywords": ["notification", "domotique", "alerte"],
    },
    "fr-FR": {
        "summary": "Notifications proactives de Home Assistant.",
        "description": "Reçoit des alertes de notification proactive de votre instance Home Assistant.",
        "keywords": ["notification", "domotique", "alerte"],
    },
    "hi-IN": {
        "summary": "Home Assistant से सक्रिय सूचनाएं।",
        "description": "आपके Home Assistant इंस्टेंस से सक्रिय सूचना अलर्ट प्राप्त करता है।",
        "keywords": ["सूचना", "होम ऑटोमेशन", "अलर्ट"],
    },
    "it-IT": {
        "summary": "Notifiche proattive da Home Assistant.",
        "description": "Ricevi avvisi di notifica proattivi dalla tua istanza Home Assistant.",
        "keywords": ["notifica", "domotica", "avviso"],
    },
    "ja-JP": {
        "summary": "Home Assistantからのプロアクティブ通知。",
        "description": "Home Assistantインスタンスからプロアクティブ通知アラートを受信します。",
        "keywords": ["通知", "ホームオートメーション", "アラート"],
    },
    "nl-NL": {
        "summary": "Proactieve meldingen van Home Assistant.",
        "description": "Ontvangt proactieve meldingswaarschuwingen van uw Home Assistant-instance.",
        "keywords": ["melding", "domotica", "waarschuwing"],
    },
    "pt-BR": {
        "summary": "Notificações proativas do Home Assistant.",
        "description": "Recebe alertas de notificação proativa da sua instância do Home Assistant.",
        "keywords": ["notificação", "automação residencial", "alerta"],
    },
}


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

    async def _async_create_skill(self, vendor_id: str, webhook_url: str, skill_name: str) -> str:
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
        """Orchestrate full skill setup: reuse existing or create, upload models, enable."""
        _LOGGER.info("SMAPI setup: webhook_url=%s, skill_name=%s", webhook_url, skill_name)
        vendor_id = await self.async_get_vendor_id()
        skill_id: str | None = None

        # Reuse existing skill if one with matching name already exists
        skill_id = await self._async_find_existing_skill(vendor_id, skill_name)
        if skill_id:
            _LOGGER.info("Reusing existing skill: %s", skill_id)
        else:
            try:
                skill_id = await self._async_create_skill(vendor_id, webhook_url, skill_name)
                _LOGGER.info("Created new skill %s, waiting for provisioning", skill_id)
                await asyncio.sleep(5)
            except HomeAssistantError as err:
                if "409" in str(err):
                    skill_id = await self._async_resolve_conflict(vendor_id, webhook_url, skill_name)
                else:
                    raise

        # Upload models concurrently and track which locales succeed
        async def _upload(locale: str, model: dict) -> str | None:
            try:
                await self.async_upload_model(skill_id, model=model, locale=locale)
                return locale
            except HomeAssistantError as err:
                _LOGGER.warning("Failed to upload model for %s (non-fatal): %s", locale, err)
                return None

        results = await asyncio.gather(*[_upload(loc, m) for loc, m in models.items()])
        successful_locales = [r for r in results if r is not None]

        # Update manifest — only include locales with working models
        if not successful_locales:
            raise HomeAssistantError("All model uploads failed — no usable locales for skill")
        manifest = self._build_manifest(webhook_url, skill_name, successful_locales)
        try:
            await self._async_request(
                "PUT",
                f"/v1/skills/{skill_id}/stages/development/manifest",
                json={"manifest": manifest},
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to update manifest (non-fatal): %s", err)

        try:
            await self.async_enable_skill(skill_id)
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to enable skill %s (non-fatal): %s", skill_id, err)

        return {"skill_id": skill_id, "vendor_id": vendor_id, "webhook_url": webhook_url}

    async def _async_find_existing_skill(self, vendor_id: str, skill_name: str) -> str | None:
        """Check if a skill with the given name already exists."""
        data = await self._async_request("GET", "/v1/skills", params={"vendorId": vendor_id})
        skills = data.get("skills", [])
        for skill in skills:
            if skill.get("stage") != "development":
                continue
            skill_id = skill.get("skillId")
            name_by_locale = skill.get("nameByLocale", {})
            if any(v.get("name") == skill_name for v in name_by_locale.values() if isinstance(v, dict)):
                _LOGGER.debug("Found matching development skill: %s", skill_id)
                return skill_id
        return None

    async def _async_resolve_conflict(self, vendor_id: str, webhook_url: str, skill_name: str) -> str:
        data = await self._async_request("GET", "/v1/skills", params={"vendorId": vendor_id})
        skills = data.get("skills", [])
        if not skills:
            raise HomeAssistantError("Skill conflict but no existing skills found")
        skill_id = skills[0]["skillId"]
        await self.async_update_manifest(skill_id, webhook_url, skill_name)
        return skill_id

    def _build_manifest(self, webhook_url: str, skill_name: str, locales: list[str] | None = None) -> dict:
        """Build the skill manifest payload."""
        target = locales if locales else list(_MANIFEST_LOCALE_INFO)
        locale_manifests = {}
        for loc in target:
            info = _MANIFEST_LOCALE_INFO[loc]
            locale_manifests[loc] = {
                "name": skill_name,
                "examplePhrases": [f"Alexa, open {skill_name}"],
                **info,
            }

        return {
            "publishingInformation": {
                "locales": locale_manifests,
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
        _LOGGER.debug("SMAPI %s %s — token prefix: %s...", method, path, token[:20] if token else "NONE")
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        if self._session is None or self._session.closed:
            from homeassistant.helpers.aiohttp_client import async_create_clientsession
            self._session = async_create_clientsession(self._hass)

        url = f"{SMAPI_BASE_URL}{path}"
        try:
            async with self._session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 401:
                    body = await resp.text()
                    _LOGGER.error("SMAPI 401 Unauthorized: %s %s — body: %s", method, path, body[:500])
                    raise HomeAssistantError(f"Invalid LWA credentials: {body[:200]}")
                if resp.status == 409:
                    text = await resp.text()
                    raise HomeAssistantError(f"Conflict (409): {text}")
                if resp.status == 204:
                    return None
                if resp.status >= 400:
                    body = await resp.text()
                    _LOGGER.error("SMAPI %s %s returned %s: %s", method, path, resp.status, body[:500])
                    raise HomeAssistantError(f"SMAPI error ({resp.status}): {body[:200]}")
                return await resp.json()
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"SMAPI request failed: {err}") from err
