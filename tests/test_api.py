"""Unit tests for the LWA OAuth2 client (api.py)."""

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant before importing api (HA is not installed).
# ---------------------------------------------------------------------------
_ha_pkg = MagicMock()
sys.modules["homeassistant"] = _ha_pkg
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.exceptions"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()

_HomeAssistantError = type("HomeAssistantError", (Exception,), {})
sys.modules["homeassistant.exceptions"].HomeAssistantError = _HomeAssistantError

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------


def _register_package(pkg_name: str) -> None:
    """Register a dummy parent package in sys.modules so relative imports resolve."""
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


def _load_submodule(module_name: str, filename: str):
    """Load a submodule from COMPONENT_DIR without normal import machinery."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    _register_package("alexa_proactive")
    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT_DIR / filename, submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_const():
    return _load_submodule("alexa_proactive.const", "const.py")


def _load_api():
    _load_const()
    return _load_submodule("alexa_proactive.api", "api.py")


# ---------------------------------------------------------------------------
# Mock response / session helpers
# ---------------------------------------------------------------------------


def _make_mock_response(json_data, status=200):
    """Build a mock aiohttp response usable as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_mock_session(mock_response):
    """Build a mock aiohttp ClientSession whose .post() returns *mock_response*."""
    mock_post = AsyncMock(return_value=mock_response)
    mock_post.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post.__aexit__ = AsyncMock(return_value=False)
    session = AsyncMock()
    session.post = MagicMock(return_value=mock_post)
    session.closed = False
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def const():
    return _load_const()


@pytest.fixture(scope="module")
def api():
    return _load_api()


@pytest.fixture
def hass():
    return MagicMock()


@pytest.fixture
def client(hass, api):
    return api.LWAClient(
        hass=hass,
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


@pytest.fixture
def successful_token_response():
    return {
        "access_token": "Atza|test_token_abc123",
        "expires_in": 3600,
        "token_type": "bearer",
    }


# ---------------------------------------------------------------------------
# Test: __init__ stores credentials
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_stores_credentials(self, client):
        assert client._client_id == "test_client_id"
        assert client._client_secret == "test_client_secret"
        assert client._hass is not None
        assert client._tokens == {}
        assert client._session is None


# ---------------------------------------------------------------------------
# Test: _async_request_token
# ---------------------------------------------------------------------------


class TestRequestToken:

    @pytest.mark.asyncio
    async def test_request_token_success(self, client, const, successful_token_response):
        mock_session = _make_mock_session(_make_mock_response(successful_token_response))

        with patch.object(client, "_session", mock_session):
            result = await client._async_request_token(const.SCOPE_PROACTIVE)

        call_args = mock_session.post.call_args
        assert call_args[0][0] == const.LWA_TOKEN_URL

        form_data = call_args[1]["data"]
        assert form_data["grant_type"] == "client_credentials"
        assert form_data["client_id"] == "test_client_id"
        assert form_data["client_secret"] == "test_client_secret"
        assert form_data["scope"] == const.SCOPE_PROACTIVE

        assert result["access_token"] == "Atza|test_token_abc123"
        assert result["expires_in"] == 3600
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_request_token_invalid_credentials(self, client, const):
        mock_session = _make_mock_session(
            _make_mock_response({"error": "invalid_client"}, status=401)
        )

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(_HomeAssistantError, match="Invalid LWA credentials"),
        ):
            await client._async_request_token(const.SCOPE_PROACTIVE)

    @pytest.mark.asyncio
    async def test_request_token_network_error(self, client, const):
        import aiohttp

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
        mock_session.closed = False

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(_HomeAssistantError, match="Cannot connect to Amazon LWA"),
        ):
            await client._async_request_token(const.SCOPE_PROACTIVE)

    @pytest.mark.asyncio
    async def test_request_token_missing_access_token(self, client, const):
        mock_session = _make_mock_session(
            _make_mock_response({"error": "unauthorized_client"})
        )

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(_HomeAssistantError, match="Missing required scope"),
        ):
            await client._async_request_token(const.SCOPE_PROACTIVE)


# ---------------------------------------------------------------------------
# Test: _async_get_token caching behaviour
# ---------------------------------------------------------------------------


class TestGetTokenCaching:

    @pytest.mark.asyncio
    async def test_get_token_caches_result(self, client, const):
        payload = {
            "access_token": "Atza|cached_token",
            "expires_in": 3600,
            "token_type": "bearer",
        }
        mock_session = _make_mock_session(_make_mock_response(payload))

        with (
            patch.object(client, "_session", mock_session),
            patch.object(
                client, "_async_request_token", wraps=client._async_request_token
            ) as spy,
        ):
            first = await client._async_get_token(const.SCOPE_PROACTIVE)
            second = await client._async_get_token(const.SCOPE_PROACTIVE)

        assert first == "Atza|cached_token"
        assert second == "Atza|cached_token"
        spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_refreshes_near_expiry(self, client, const):
        client._tokens[const.SCOPE_PROACTIVE] = {
            "access_token": "Atza|expired_token",
            "expires_at": time.monotonic() - 10,
        }

        fresh_payload = {
            "access_token": "Atza|fresh_token",
            "expires_in": 3600,
            "token_type": "bearer",
        }
        mock_session = _make_mock_session(_make_mock_response(fresh_payload))

        with patch.object(client, "_session", mock_session):
            token = await client._async_get_token(const.SCOPE_PROACTIVE)

        assert token == "Atza|fresh_token"
        mock_session.post.assert_called_once()


# ---------------------------------------------------------------------------
# Test: public convenience methods use correct scopes
# ---------------------------------------------------------------------------


class TestPublicMethods:

    @pytest.mark.asyncio
    async def test_get_proactive_token_scope(self, client, const):
        with patch.object(
            client, "_async_get_token", new_callable=AsyncMock, return_value="tok"
        ) as mock_get:
            result = await client.async_get_proactive_token()

        mock_get.assert_called_once_with(const.SCOPE_PROACTIVE)
        assert result == "tok"

    @pytest.mark.asyncio
    async def test_get_smapi_token_scope(self, client, const):
        with patch.object(
            client, "_async_get_token", new_callable=AsyncMock, return_value="tok"
        ) as mock_get:
            result = await client.async_get_smapi_token()

        mock_get.assert_called_once_with(const.SCOPE_SMAPI)
        assert result == "tok"
