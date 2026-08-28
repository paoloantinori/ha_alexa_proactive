"""Integration tests for HTTP views (AlexaProactiveView, AlexaAuthCallbackView)."""
from __future__ import annotations

import pytest

from custom_components.alexa_proactive.const import CONF_ALEXA_USER_ID, DOMAIN
from custom_components.alexa_proactive.views import AlexaAuthCallbackView


def _launch_request(user_id: str = "amzn1.ask.user.test123") -> dict:
    return {
        "request": {"type": "LaunchRequest"},
        "session": {"user": {"userId": user_id}},
    }


def _intent_request(intent_name: str) -> dict:
    return {
        "request": {"type": "IntentRequest", "intent": {"name": intent_name}},
        "session": {"user": {"userId": "amzn1.ask.user.test"}},
    }


def _session_ended_request() -> dict:
    return {"request": {"type": "SessionEndedRequest"}, "session": {}}


# ---------------------------------------------------------------------------
# AlexaProactiveView
# ---------------------------------------------------------------------------


async def test_launch_request(setup_entry, hass_client_no_auth):
    """LaunchRequest returns welcome message."""
    hass, entry = setup_entry
    client = await hass_client_no_auth()

    resp = await client.post("/api/alexa_proactive", json=_launch_request())
    assert resp.status == 200
    body = await resp.json()
    assert body["version"] == "1.0"
    assert "Welcome" in body["response"]["outputSpeech"]["text"]


async def test_launch_request_captures_user_id(setup_entry, hass_client_no_auth):
    """LaunchRequest persists the Alexa user ID into the config entry."""
    hass, entry = setup_entry
    client = await hass_client_no_auth()

    test_user_id = "amzn1.ask.user.captured_id"
    await client.post("/api/alexa_proactive", json=_launch_request(user_id=test_user_id))
    await hass.async_block_till_done()

    assert entry.data.get(CONF_ALEXA_USER_ID) == test_user_id


async def test_send_notification_intent(setup_entry, hass_client_no_auth):
    """SendNotificationIntent returns user ID captured message."""
    _, _ = setup_entry
    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/alexa_proactive", json=_intent_request("SendNotificationIntent")
    )
    assert resp.status == 200
    body = await resp.json()
    assert "user ID has been captured" in body["response"]["outputSpeech"]["text"]


async def test_check_status_intent(setup_entry, hass_client_no_auth):
    """CheckStatusIntent returns active skill message."""
    _, _ = setup_entry
    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/alexa_proactive", json=_intent_request("CheckStatusIntent")
    )
    assert resp.status == 200
    body = await resp.json()
    assert "active" in body["response"]["outputSpeech"]["text"].lower()


async def test_session_ended_request(setup_entry, hass_client_no_auth):
    """SessionEndedRequest returns empty response."""
    _, _ = setup_entry
    client = await hass_client_no_auth()

    resp = await client.post("/api/alexa_proactive", json=_session_ended_request())
    assert resp.status == 200
    body = await resp.json()
    assert body["response"] == {}


async def test_unknown_request_type(setup_entry, hass_client_no_auth):
    """Unknown request type returns reprompt."""
    _, _ = setup_entry
    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/alexa_proactive",
        json={"request": {"type": "UnknownType"}, "session": {}},
    )
    assert resp.status == 200
    body = await resp.json()
    assert "reprompt" in body["response"]


# ---------------------------------------------------------------------------
# AlexaAuthCallbackView
# ---------------------------------------------------------------------------


async def test_callback_stores_auth_code(hass_with_http, hass_client_no_auth):
    """Callback stores the auth code in hass.data."""
    hass = hass_with_http
    hass.http.register_view(AlexaAuthCallbackView(hass))
    client = await hass_client_no_auth()

    resp = await client.get(
        "/auth/alexa_proactive/callback",
        params={"code": "test_auth_code", "state": "flow123_smapi"},
    )
    assert resp.status == 200
    text = await resp.text()
    assert "Authorization successful" in text
    assert hass.data[DOMAIN]["auth_codes"]["flow123_smapi"] == "test_auth_code"


async def test_callback_error_param(hass_with_http, hass_client_no_auth):
    """Callback returns error HTML when error param is present."""
    hass = hass_with_http
    hass.http.register_view(AlexaAuthCallbackView(hass))
    client = await hass_client_no_auth()

    resp = await client.get(
        "/auth/alexa_proactive/callback",
        params={"error": "access_denied", "error_description": "User denied"},
    )
    assert resp.status == 400
    text = await resp.text()
    assert "Authorization failed" in text


async def test_callback_missing_params(hass_with_http, hass_client_no_auth):
    """Callback returns 400 when required params are missing."""
    hass = hass_with_http
    hass.http.register_view(AlexaAuthCallbackView(hass))
    client = await hass_client_no_auth()

    resp = await client.get(
        "/auth/alexa_proactive/callback",
        params={"code": "abc"},
    )
    assert resp.status == 400
