"""Unit tests for the Proactive Events API client (proactive.py)."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


def _load_proactive():
    _register_package("alexa_proactive")
    mod_name = "alexa_proactive.proactive"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name, COMPONENT_DIR / "proactive.py", submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_hass():
    hass = MagicMock()
    return hass


def _make_lwa(token="test-token"):
    lwa = MagicMock()
    lwa.async_get_proactive_token = AsyncMock(return_value=token)
    return lwa


def _make_client(hass=None, lwa=None, region="eu"):
    proactive_mod = _load_proactive()
    return proactive_mod.ProactiveClient(hass or _make_hass(), lwa or _make_lwa(), region)


def _mock_post_response(status=200, body=None):
    """Create a mock aiohttp response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body or "")
    resp.json = AsyncMock(return_value=body or {})
    resp.raise_for_status = MagicMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def proactive_mod():
    return _load_proactive()


@pytest.fixture
def hass():
    return _make_hass()


@pytest.fixture
def lwa():
    return _make_lwa()


@pytest.fixture
def client(hass, lwa):
    return _make_client(hass, lwa, "eu")


# ---------------------------------------------------------------------------
# Test: payload building
# ---------------------------------------------------------------------------


class TestBuildPayload:

    def test_multicast_audience(self, client):
        payload = client._build_payload("Home Assistant", 1, None)
        assert payload["relevantAudience"]["type"] == "Multicast"
        assert payload["relevantAudience"]["payload"] == {}

    def test_unicast_audience(self, client):
        payload = client._build_payload("HA", 3, "amzn1.ask.account.ABC")
        assert payload["relevantAudience"]["type"] == "Unicast"
        assert payload["relevantAudience"]["payload"]["user"] == "amzn1.ask.account.ABC"

    def test_event_name(self, client):
        payload = client._build_payload("HA", 1, None)
        assert payload["event"]["name"] == "AMAZON.MessageAlert.Activated"

    def test_message_state(self, client):
        payload = client._build_payload("HA", 1, None)
        state = payload["event"]["payload"]["state"]
        assert state["status"] == "UNREAD"
        assert state["freshness"] == "NEW"

    def test_sender_name_in_payload(self, client):
        payload = client._build_payload("Kitchen Alert", 1, None)
        assert payload["event"]["payload"]["messageGroup"]["creator"]["name"] == "Kitchen Alert"

    def test_count_in_payload(self, client):
        payload = client._build_payload("HA", 5, None)
        assert payload["event"]["payload"]["messageGroup"]["count"] == 5

    def test_reference_id_format(self, client):
        payload = client._build_payload("HA", 1, None)
        ref = payload["referenceId"]
        assert ref.startswith("pingme-")
        parts = ref.split("-")
        assert len(parts) == 3

    def test_timestamp_is_iso_format(self, client):
        payload = client._build_payload("HA", 1, None)
        ts = payload["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_expiry_time_in_future(self, client):
        payload = client._build_payload("HA", 1, None)
        now = datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(payload["expiryTime"])
        assert expiry > now
        delta = expiry - datetime.fromisoformat(payload["timestamp"])
        assert 3590 < delta.total_seconds() < 3610


# ---------------------------------------------------------------------------
# Test: API URL
# ---------------------------------------------------------------------------


class TestApiUrl:

    def test_eu_region(self, client):
        assert "api.eu.amazonalexa.com" in client._api_url()

    def test_na_region(self):
        client = _make_client(region="na")
        assert "api.amazonalexa.com" in client._api_url()
        assert "api.eu" not in client._api_url()

    def test_fe_region(self):
        client = _make_client(region="fe")
        assert "api.fe.amazonalexa.com" in client._api_url()

    def test_url_contains_proactive_events_path(self, client):
        assert "/v1/proactiveEvents/stages/development" in client._api_url()


# ---------------------------------------------------------------------------
# Test: async_send
# ---------------------------------------------------------------------------


class TestAsyncSend:

    @pytest.mark.asyncio
    async def test_successful_send(self, client):
        cm = _mock_post_response(200, {})
        with patch.object(client, "_async_post", return_value={}):
            result = await client.async_send(sender="Test", count=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_send_gets_token(self, client, lwa):
        with patch.object(client, "_async_post", return_value={}):
            await client.async_send(sender="Test", count=1)
        lwa.async_get_proactive_token.assert_called()

    @pytest.mark.asyncio
    async def test_send_unicast_passes_user_id(self, client):
        payload = client._build_payload("HA", 1, "user123")
        assert payload["relevantAudience"]["type"] == "Unicast"

    @pytest.mark.asyncio
    async def test_retry_on_forbidden(self, client, lwa, ha_error):
        call_count = 0
        original_post = client._async_post

        async def failing_post(token, payload):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ha_error("403 forbidden")
            return {}

        client._async_post = failing_post
        result = await client.async_send(sender="HA", count=1)
        assert call_count == 2
        assert lwa.async_get_proactive_token.call_count == 2


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_400_raises_error(self, client, ha_error):
        resp = MagicMock()
        resp.status = 400
        resp.text = AsyncMock(return_value="invalid payload details")
        resp.json = AsyncMock(return_value={})

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=cm)
        mock_session.closed = False
        client._session = mock_session

        with pytest.raises(ha_error):
            await client._async_post("token", {})

    @pytest.mark.asyncio
    async def test_network_error_raises(self, client, ha_error):
        import aiohttp as _aiohttp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=_aiohttp.ClientError("connection refused"))
        mock_session.closed = False
        client._session = mock_session

        with pytest.raises(ha_error):
            await client._async_post("token", {})
