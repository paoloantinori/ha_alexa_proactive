"""SMAPI client for automated Alexa skill management."""
from __future__ import annotations

import asyncio
import json
import logging
import time

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
        if not isinstance(data, dict):
            raise HomeAssistantError("Unexpected response from vendor list API")
        vendors = data.get("vendors", [])
        if not vendors:
            raise HomeAssistantError("No Amazon vendor account found")
        return vendors[0]["id"]

    async def _async_create_skill(self, vendor_id: str, webhook_url: str, skill_name: str, locales: list[str] | None = None) -> str:
        manifest = await self._build_manifest(webhook_url, skill_name, locales)
        data = await self._async_request("POST", "/v1/skills", json={"vendorId": vendor_id, "manifest": manifest})
        if not isinstance(data, dict) or "skillId" not in data:
            raise HomeAssistantError("Skill creation did not return a skill ID")
        return data["skillId"]

    async def async_update_manifest(self, skill_id: str, webhook_url: str, skill_name: str = "Home Assistant") -> None:
        manifest = await self._build_manifest(webhook_url, skill_name)
        await self._async_request(
            "PUT",
            f"/v1/skills/{skill_id}/stages/development/manifest",
            json={"manifest": manifest},
            headers={"If-Match": "*"},
        )

    async def async_upload_model(self, skill_id: str, locale: str, model: dict) -> None:
        headers: dict[str, str] = {}
        try:
            existing = await self._async_request(
                "GET",
                f"/v1/skills/{skill_id}/stages/development/interactionModel/locales/{locale}",
            )
            if isinstance(existing, dict) and "eTag" in existing:
                headers["If-Match"] = existing["eTag"]
        except HomeAssistantError:
            pass

        await self._async_request(
            "PUT",
            f"/v1/skills/{skill_id}/stages/development/interactionModel/locales/{locale}",
            json=model,
            headers=headers,
        )

    async def async_enable_skill(self, skill_id: str) -> None:
        await self._async_request("PUT", f"/v1/skills/{skill_id}/stages/development/enablement", json={})

    async def async_get_skill_credentials(self, skill_id: str) -> dict:
        data = await self._async_request("GET", f"/v1/skills/{skill_id}/credentials")
        if not isinstance(data, dict):
            return {"client_id": None, "client_secret": None}
        creds = data.get("skillMessagingCredentials", {})
        return {
            "client_id": creds.get("clientId"),
            "client_secret": creds.get("clientSecret"),
        }

    async def async_get_skill_status(self, skill_id: str) -> dict:
        data = await self._async_request("GET", f"/v1/skills/{skill_id}/status")
        return data if isinstance(data, dict) else {}

    async def async_wait_for_model_build(
        self,
        skill_id: str,
        locales: list[str],
        timeout: float = 180.0,
        poll_interval: float = 5.0,
    ) -> list[str]:
        """Poll skill status until at least one locale build reaches SUCCEEDED."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                data = await self.async_get_skill_status(skill_id)
                _LOGGER.warning("RAW skill status for %s: %s", skill_id, json.dumps(data))
            except HomeAssistantError as err:
                _LOGGER.warning("Skill status poll failed (will retry): %s", err)
                await asyncio.sleep(poll_interval)
                continue

            # SMAPI returns locales either under interactionModel.locales.{locale}
            # (documented) or directly under interactionModel.{locale} (observed
            # in practice). Handle both so we don't miss a SUCCEEDED build.
            interaction = data.get("interactionModel", {})
            locale_statuses = interaction.get("locales") or interaction
            succeeded: list[str] = []
            failed: list[str] = []
            pending: list[str] = []

            for locale in locales:
                status = locale_statuses.get(locale, {}).get("lastUpdateRequest", {}).get("status", "")
                if status == "SUCCEEDED":
                    succeeded.append(locale)
                elif status == "FAILED":
                    failed.append(locale)
                else:
                    pending.append(locale)

            _LOGGER.warning(
                "Skill %s build status — succeeded: %s, failed: %s, pending: %s",
                skill_id, succeeded, failed, pending,
            )

            if succeeded:
                return succeeded
            if not pending:
                break
            elapsed = deadline - time.monotonic()
            if elapsed > poll_interval:
                await asyncio.sleep(poll_interval)
            else:
                break

        raise HomeAssistantError(
            f"Model build timed out after {timeout}s — no locales reached SUCCEEDED"
        )

    async def async_setup_skill_complete(
        self,
        webhook_url: str,
        models: dict[str, dict],
        skill_name: str = "Home Assistant",
    ) -> dict:
        """Orchestrate full skill setup: reuse existing or create, upload models, enable."""
        _LOGGER.warning("SMAPI setup: webhook_url=%s, skill_name=%s", webhook_url, skill_name)
        vendor_id = await self.async_get_vendor_id()
        skill_id: str | None = None
        selected_locales = list(models.keys())

        # Reuse existing skill if one with matching name already exists
        skill_id = await self._async_find_existing_skill(vendor_id, skill_name)
        if skill_id:
            _LOGGER.warning("Reusing existing skill: %s", skill_id)
        else:
            try:
                skill_id = await self._async_create_skill(vendor_id, webhook_url, skill_name, selected_locales)
                _LOGGER.warning("Created new skill %s, waiting for provisioning", skill_id)
                await asyncio.sleep(5)
            except HomeAssistantError as err:
                if "409" in str(err):
                    skill_id = await self._async_resolve_conflict(vendor_id, webhook_url, skill_name)
                else:
                    raise

        # Upload models concurrently with retry, track which locales succeed
        _MAX_RETRIES = 2

        async def _upload(locale: str, model: dict) -> str | None:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    await self.async_upload_model(skill_id, model=model, locale=locale)
                    return locale
                except HomeAssistantError as err:
                    if attempt < _MAX_RETRIES:
                        _LOGGER.debug("Model upload for %s failed (attempt %d), retrying: %s", locale, attempt + 1, err)
                        await asyncio.sleep(2)
                    else:
                        _LOGGER.warning("Failed to upload model for %s after %d attempts: %s", locale, _MAX_RETRIES + 1, err)
                        return None

        upload_locales: list[str] = []
        results = await asyncio.gather(*(_upload(loc, m) for loc, m in models.items()))
        upload_locales = [r for r in results if r is not None]

        if not upload_locales:
            raise HomeAssistantError("All model uploads failed — no usable locales for skill")

        # Update manifest with uploaded locales (builds happen asynchronously on Amazon's side)
        manifest = await self._build_manifest(webhook_url, skill_name, upload_locales)
        try:
            await self._async_request(
                "PUT",
                f"/v1/skills/{skill_id}/stages/development/manifest",
                json={"manifest": manifest},
                headers={"If-Match": "*"},
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to update manifest (non-fatal): %s", err)

        # Wait for Amazon to finish building the interaction model before
        # enabling. Enablement 403s ("Custom skills must have an interaction
        # model") if attempted before the async build completes.
        build_succeeded = True
        try:
            built_locales = await self.async_wait_for_model_build(
                skill_id, upload_locales
            )
            _LOGGER.warning(
                "Interaction model build SUCCEEDED for %s; proceeding to enable",
                built_locales,
            )
        except HomeAssistantError as err:
            build_succeeded = False
            _LOGGER.warning(
                "Model build did not complete in time (will still try to enable): %s",
                err,
            )

        try:
            await self.async_enable_skill(skill_id)
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to enable skill %s (will need manual enable in Alexa app): %s", skill_id, err)

        return {
            "skill_id": skill_id,
            "vendor_id": vendor_id,
            "webhook_url": webhook_url,
            "build_succeeded": build_succeeded,
        }

    async def _async_find_existing_skill(self, vendor_id: str, skill_name: str) -> str | None:
        """Check if a skill with the given name already exists."""
        data = await self._async_request("GET", "/v1/skills", params={"vendorId": vendor_id})
        if not isinstance(data, dict):
            return None
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
        if not isinstance(data, dict):
            raise HomeAssistantError("Skill conflict but no existing skills found")
        skills = data.get("skills", [])
        if not skills:
            raise HomeAssistantError("Skill conflict but no existing skills found")
        skill_id = skills[0]["skillId"]
        await self.async_update_manifest(skill_id, webhook_url, skill_name)
        return skill_id

    async def _detect_ssl_type(self, webhook_url: str) -> str:
        """Detect SSL certificate type by probing the endpoint."""
        import ssl
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(webhook_url)
        hostname = parsed.hostname
        if not hostname:
            return "Trusted"

        def _probe() -> str:
            try:
                ctx = ssl.create_default_context()
                with socket.create_connection((hostname, 443), timeout=5) as sock:
                    with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert() or {}
                        sans = cert.get("subjectAltName", ())
                        for entry in sans:
                            if isinstance(entry, tuple) and entry[0] == "DNS" and entry[1].startswith("*."):
                                return "Wildcard"
            except Exception as err:
                _LOGGER.warning("SSL type detection failed for %s, defaulting to 'Trusted': %s", webhook_url, err)
            return "Trusted"

        return await self._hass.async_add_executor_job(_probe)

    async def _build_manifest(self, webhook_url: str, skill_name: str, locales: list[str] | None = None) -> dict:
        """Build the skill manifest payload."""
        ssl_type = await self._detect_ssl_type(webhook_url)
        _LOGGER.info("Detected SSL certificate type: %s for %s", ssl_type, webhook_url)

        target = locales if locales else list(_MANIFEST_LOCALE_INFO)
        locale_manifests = {}
        for loc in target:
            info = _MANIFEST_LOCALE_INFO[loc]
            locale_manifests[loc] = {
                "name": skill_name,
                "examplePhrases": [f"Alexa, open {skill_name}"],
                **info,
            }

        endpoint = {"sslCertificateType": ssl_type, "uri": webhook_url}
        regions = {
            "NA": {"endpoint": endpoint},
            "EU": {"endpoint": endpoint},
            "FE": {"endpoint": endpoint},
        }

        return {
            "publishingInformation": {
                "locales": locale_manifests,
                "isAvailableWorldwide": True,
                "testingInstructions": f"Say 'Alexa, open {skill_name}'. Check for notification.",
            },
            "apis": {
                "custom": {
                    "endpoint": endpoint,
                    "regions": regions,
                    "interfaces": [],
                }
            },
            "manifestVersion": "1.0",
            "permissions": [{"name": "alexa::devices:all:notifications:write"}],
            "events": {
                "publications": [{"eventName": EVENT_SCHEMA}],
                "subscriptions": [{"eventName": "SKILL_PROACTIVE_SUBSCRIPTION_CHANGED"}],
                "endpoint": endpoint,
                "regions": regions,
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
            connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
            self._session = aiohttp.ClientSession(connector=connector)

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
