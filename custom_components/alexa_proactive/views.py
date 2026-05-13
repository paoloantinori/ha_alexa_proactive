"""Custom HTTP view acting as the Alexa skill endpoint."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import json_bytes

from .const import CONF_ALEXA_USER_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _speech_response(text: str, *, end_session: bool = True, reprompt: str | None = None) -> dict:
    response: dict = {
        "outputSpeech": {"type": "PlainText", "text": text},
        "shouldEndSession": end_session,
    }
    if reprompt:
        response["reprompt"] = {"outputSpeech": {"type": "PlainText", "text": reprompt}}
    return {"version": "1.0", "response": response, "sessionAttributes": {}}


_EMPTY_RESPONSE = {"version": "1.0", "response": {}}


class AlexaProactiveView(HomeAssistantView):
    url = "/api/alexa_proactive"
    name = "api:alexa_proactive"
    requires_auth = False
    cors_allowed = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    @staticmethod
    def _alexa_json(result: dict) -> web.Response:
        """Return JSON response without gzip compression.

        HomeAssistantView.json() calls enable_compression() which gzip-compresses
        the body. Amazon's Alexa skill dispatcher fails to parse compressed responses,
        causing INVALID_RESPONSE errors on Echo devices.
        """
        return web.Response(body=json_bytes(result), content_type="application/json")

    async def post(self, request: web.Request) -> web.Response:
        _LOGGER.warning("Alexa POST received from %s", request.remote)
        try:
            event = await request.json()
        except Exception:
            return self._alexa_json(_speech_response("Sorry, something went wrong."))

        req = event.get("request", {})
        request_type = req.get("type", "")
        intent = req.get("intent") or {}
        intent_name = intent.get("name", "")

        user_id = ""
        session = event.get("session") or {}
        if session.get("user"):
            user_id = session["user"].get("userId", "")

        _LOGGER.debug("%s%s", request_type, f" / {intent_name}" if intent_name else "")

        if user_id:
            _LOGGER.debug("  userId: %s", user_id)

        handler = {
            "LaunchRequest": self._handle_launch,
            "IntentRequest": self._handle_intent,
            "SessionEndedRequest": lambda r, u: _EMPTY_RESPONSE,
            "System.ExceptionEncountered": self._handle_exception,
            "AlexaSkillEvent.SkillProactiveSubscriptionChanged": self._handle_subscription_changed,
        }.get(request_type)

        if handler is None:
            _LOGGER.warning("Unknown request type: %s", request_type)
            return self._alexa_json(_speech_response("Say send notification or check status.", end_session=False, reprompt="What would you like to do?"))

        result = handler(req, user_id)
        if user_id and request_type == "LaunchRequest":
            self._store_user_id(user_id)

        _LOGGER.warning("Alexa responding to %s: %s", request_type, str(result)[:300])
        return self._alexa_json(result)

    def _handle_launch(self, request: dict, user_id: str) -> dict:
        return _speech_response("Welcome to Ping Me! You are set up for proactive notifications.")

    def _handle_intent(self, request: dict, user_id: str) -> dict:
        intent_name = (request.get("intent") or {}).get("name", "")

        if intent_name == "SendNotificationIntent":
            return _speech_response("Your user ID has been captured. Use the notification script to send a proactive alert.")

        if intent_name == "CheckStatusIntent":
            return _speech_response("Your skill is active. Enable notifications in the Alexa app to receive proactive alerts.")

        if intent_name in ("AMAZON.HelpIntent",):
            return _speech_response("Say send notification or check status.", end_session=False, reprompt="What would you like to do?")

        if intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return _speech_response("", end_session=True)

        return _speech_response("Say send notification or check status.", end_session=False, reprompt="What would you like to do?")

    def _handle_exception(self, request: dict, user_id: str) -> dict:
        cause = request.get("cause", {})
        _LOGGER.error("Alexa exception: %s", cause.get("message", "unknown"))
        return _EMPTY_RESPONSE

    def _handle_subscription_changed(self, request: dict, user_id: str) -> dict:
        body = request.get("body", {})
        subscriptions = body.get("subscriptions", [])
        _LOGGER.info("Proactive subscription changed: %s", subscriptions)
        return _EMPTY_RESPONSE

    def _store_user_id(self, user_id: str) -> None:
        entries = self._hass.data.get(DOMAIN)
        if not entries:
            return
        for key, entry_data in entries.items():
            if isinstance(entry_data, dict) and key not in ("auth_codes", "_callback_registered"):
                entry_data[CONF_ALEXA_USER_ID] = user_id


class AlexaAuthCallbackView(HomeAssistantView):
    """Receives the OAuth2 redirect from Amazon after user authorizes."""

    url = "/auth/alexa_proactive/callback"
    name = "auth:alexa_proactive:callback"
    requires_auth = False
    cors_allowed = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        if error:
            _LOGGER.error("LWA auth error: %s", request.query.get("error_description", error))
            return web.Response(
                text="<html><body><h2>Authorization failed</h2><p>Please try again.</p></body></html>",
                content_type="text/html",
                status=400,
            )

        if not code or not state:
            return web.Response(text="Missing parameters.", content_type="text/html", status=400)

        self._hass.data.setdefault(DOMAIN, {}).setdefault("auth_codes", {})[state] = code
        all_codes = self._hass.data.get(DOMAIN, {}).get("auth_codes", {})
        _LOGGER.info("LWA auth code received: state=%s, all_keys=%s", state, list(all_codes.keys()))

        return web.Response(
            text="<html><body><h2>Authorization successful!</h2>"
            "<p>You can close this tab and return to Home Assistant to complete setup.</p></body></html>",
            content_type="text/html",
        )
