"""Unit tests for the Alexa skill HTTP view (views.py)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


def _register_package(pkg_name: str) -> None:
    if pkg_name in sys.modules:
        return
    pkg = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            pkg_name, COMPONENT_DIR / "__init__.py", submodule_search_locations=[]
        )
    )
    pkg.__package__ = pkg_name
    pkg.__path__ = [str(COMPONENT_DIR)]
    sys.modules[pkg_name] = pkg


def _load_views():
    _register_package("alexa_proactive")
    module_name = "alexa_proactive.views"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT_DIR / "views.py", submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_hass():
    hass = MagicMock()
    hass.data = {"alexa_proactive": {"entry_abc": {}}}
    return hass


def _make_request(event: dict):
    """Create a mock aiohttp Request with a JSON body."""
    request = MagicMock()
    request.json = AsyncMock(return_value=event)
    return request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def views_mod():
    return _load_views()


@pytest.fixture
def hass():
    return _make_hass()


@pytest.fixture
def view(views_mod, hass):
    return views_mod.AlexaProactiveView(hass)


# ---------------------------------------------------------------------------
# Test: view attributes
# ---------------------------------------------------------------------------


class TestViewAttributes:

    def test_url(self, view):
        assert view.url == "/api/alexa_proactive"

    def test_name(self, view):
        assert view.name == "api:alexa_proactive"

    def test_no_auth_required(self, view):
        assert view.requires_auth is False


# ---------------------------------------------------------------------------
# Test: LaunchRequest
# ---------------------------------------------------------------------------


class TestLaunchRequest:

    @pytest.mark.asyncio
    async def test_welcome_message(self, view):
        event = {
            "request": {"type": "LaunchRequest"},
            "session": {"user": {"userId": "amzn1.ask.user.test"}},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["outputSpeech"]["text"] == "Welcome to Ping Me! You are set up for proactive notifications."
        assert body["response"]["shouldEndSession"] is True

    @pytest.mark.asyncio
    async def test_captures_user_id(self, view, hass):
        entry = MagicMock()
        entry.data = {"skill_id": "amzn1.ask.skill.123"}
        hass.config_entries.async_entries = MagicMock(return_value=[entry])

        event = {
            "request": {"type": "LaunchRequest"},
            "session": {"user": {"userId": "amzn1.ask.user.abc123"}},
        }
        await view.post(_make_request(event))

        hass.config_entries.async_update_entry.assert_called_once_with(
            entry, data={"skill_id": "amzn1.ask.skill.123", "alexa_user_id": "amzn1.ask.user.abc123"}
        )


# ---------------------------------------------------------------------------
# Test: IntentRequest
# ---------------------------------------------------------------------------


class TestIntentRequest:

    @pytest.mark.asyncio
    async def test_send_notification_intent(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "SendNotificationIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        text = body["response"]["outputSpeech"]["text"]
        assert "user ID has been captured" in text

    @pytest.mark.asyncio
    async def test_check_status_intent(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "CheckStatusIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        text = body["response"]["outputSpeech"]["text"]
        assert "skill is active" in text

    @pytest.mark.asyncio
    async def test_help_intent(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "AMAZON.HelpIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["shouldEndSession"] is False
        assert "reprompt" in body["response"]

    @pytest.mark.asyncio
    async def test_cancel_intent(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "AMAZON.CancelIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["shouldEndSession"] is True

    @pytest.mark.asyncio
    async def test_stop_intent(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "AMAZON.StopIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["shouldEndSession"] is True

    @pytest.mark.asyncio
    async def test_unknown_intent_returns_help(self, view):
        event = {
            "request": {"type": "IntentRequest", "intent": {"name": "SomeRandomIntent"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["shouldEndSession"] is False
        assert "reprompt" in body["response"]


# ---------------------------------------------------------------------------
# Test: SessionEndedRequest
# ---------------------------------------------------------------------------


class TestSessionEndedRequest:

    @pytest.mark.asyncio
    async def test_returns_empty_response(self, view):
        event = {"request": {"type": "SessionEndedRequest"}, "session": {}}
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"] == {}


# ---------------------------------------------------------------------------
# Test: System.ExceptionEncountered
# ---------------------------------------------------------------------------


class TestExceptionEncountered:

    @pytest.mark.asyncio
    async def test_returns_empty_response(self, view):
        event = {
            "request": {"type": "System.ExceptionEncountered", "cause": {"message": "timeout"}},
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"] == {}


# ---------------------------------------------------------------------------
# Test: ProactiveSubscriptionChanged
# ---------------------------------------------------------------------------


class TestSubscriptionChanged:

    @pytest.mark.asyncio
    async def test_returns_empty_response(self, view):
        event = {
            "request": {
                "type": "AlexaSkillEvent.SkillProactiveSubscriptionChanged",
                "body": {"subscriptions": [{"eventName": "AMAZON.MessageAlert.Activated"}]},
            },
            "session": {},
        }
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"] == {}


# ---------------------------------------------------------------------------
# Test: Unknown request type
# ---------------------------------------------------------------------------


class TestUnknownRequestType:

    @pytest.mark.asyncio
    async def test_returns_help_with_reprompt(self, view):
        event = {"request": {"type": "SomethingWeird"}, "session": {}}
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["response"]["shouldEndSession"] is False
        assert "reprompt" in body["response"]


# ---------------------------------------------------------------------------
# Test: Malformed JSON
# ---------------------------------------------------------------------------


class TestMalformedJson:

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, view):
        request = MagicMock()
        request.json = AsyncMock(side_effect=Exception("bad json"))
        resp = await view.post(request)
        body = json.loads(resp.body)
        assert "Sorry" in body["response"]["outputSpeech"]["text"]


# ---------------------------------------------------------------------------
# Test: Response format
# ---------------------------------------------------------------------------


class TestResponseFormat:

    @pytest.mark.asyncio
    async def test_version_field(self, view):
        event = {"request": {"type": "LaunchRequest"}, "session": {}}
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert body["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_speech_response_has_session_attributes(self, view):
        event = {"request": {"type": "LaunchRequest"}, "session": {}}
        resp = await view.post(_make_request(event))
        body = json.loads(resp.body)
        assert "sessionAttributes" in body


# ---------------------------------------------------------------------------
# Helpers: AlexaAuthCallbackView
# ---------------------------------------------------------------------------


def _make_callback_hass():
    """Create a mock hass with empty data for auth callback tests."""
    hass = MagicMock()
    hass.data = {}
    return hass


def _make_get_request(query: dict):
    """Create a mock aiohttp Request with query parameters for GET."""
    import aiohttp

    request = MagicMock(spec=aiohttp.web.Request)
    request.query = query
    return request


@pytest.fixture
def callback_hass():
    return _make_callback_hass()


@pytest.fixture
def callback_view(views_mod, callback_hass):
    return views_mod.AlexaAuthCallbackView(callback_hass)


# ---------------------------------------------------------------------------
# Test: AlexaAuthCallbackView attributes
# ---------------------------------------------------------------------------


class TestAuthCallbackViewAttributes:

    def test_url(self, callback_view):
        assert callback_view.url == "/auth/alexa_proactive/callback"

    def test_name(self, callback_view):
        assert callback_view.name == "auth:alexa_proactive:callback"

    def test_no_auth_required(self, callback_view):
        assert callback_view.requires_auth is False


# ---------------------------------------------------------------------------
# Test: AlexaAuthCallbackView success
# ---------------------------------------------------------------------------


class TestAuthCallbackSuccess:

    @pytest.mark.asyncio
    async def test_stores_code_in_hass_data(self, callback_view, callback_hass):
        request = _make_get_request({"code": "abc", "state": "flow123_smapi"})
        await callback_view.get(request)
        assert callback_hass.data["alexa_proactive"]["auth_codes"]["flow123_smapi"] == "abc"

    @pytest.mark.asyncio
    async def test_returns_success_html(self, callback_view):
        request = _make_get_request({"code": "abc", "state": "flow123_smapi"})
        resp = await callback_view.get(request)
        assert resp.status == 200
        assert "successful" in resp.text

    @pytest.mark.asyncio
    async def test_state_key_format_matches_config_flow(self, callback_view, callback_hass):
        """Verify state key stored as '{flow_id}_smapi' matches config_flow lookup pattern."""
        flow_id = "a1b2c3d4"
        state_key = f"{flow_id}_smapi"
        request = _make_get_request({"code": "secret_code", "state": state_key})
        await callback_view.get(request)
        auth_codes = callback_hass.data["alexa_proactive"]["auth_codes"]
        assert state_key in auth_codes
        assert auth_codes[state_key] == "secret_code"


# ---------------------------------------------------------------------------
# Test: AlexaAuthCallbackView errors
# ---------------------------------------------------------------------------


class TestAuthCallbackError:

    @pytest.mark.asyncio
    async def test_error_param_returns_400(self, callback_view):
        request = _make_get_request({"error": "access_denied"})
        resp = await callback_view.get(request)
        assert resp.status == 400
        assert "Authorization failed" in resp.text

    @pytest.mark.asyncio
    async def test_error_with_description(self, callback_view):
        request = _make_get_request(
            {"error": "server_error", "error_description": "something went wrong"}
        )
        resp = await callback_view.get(request)
        assert resp.status == 400
        assert "Authorization failed" in resp.text

    @pytest.mark.asyncio
    async def test_missing_code_returns_400(self, callback_view):
        request = _make_get_request({"state": "flow123_smapi"})
        resp = await callback_view.get(request)
        assert resp.status == 400
        assert "Missing parameters" in resp.text

    @pytest.mark.asyncio
    async def test_missing_state_returns_400(self, callback_view):
        request = _make_get_request({"code": "abc"})
        resp = await callback_view.get(request)
        assert resp.status == 400
