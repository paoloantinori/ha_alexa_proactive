"""Unit tests for the LWA OAuth2 client (api.py) — Authorization Code flow."""
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------


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


def _load_submodule(module_name: str, filename: str):
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
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_mock_session(mock_response):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=ctx)
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
def client_with_refresh(hass, api, const):
    c = api.LWAClient(hass=hass, client_id="test_client_id", client_secret="test_client_secret")
    c.set_refresh_token(const.SCOPE_PROACTIVE, "test_refresh_proactive")
    c.set_refresh_token(const.SCOPE_SMAPI, "test_refresh_smapi")
    return c


# ---------------------------------------------------------------------------
# Test: __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_stores_credentials(self, client):
        assert client._client_id == "test_client_id"
        assert client._client_secret == "test_client_secret"
        assert client._tokens == {}
        assert client._refresh_tokens == {}
        assert client._session is None


# ---------------------------------------------------------------------------
# Test: get_authorization_url
# ---------------------------------------------------------------------------


class TestGetAuthorizationUrl:

    def test_returns_correct_url(self, client, const):
        url = client.get_authorization_url(
            "https://localhost:8123/auth/alexa_proactive/callback",
            const.SCOPE_SMAPI,
        )
        assert url.startswith("https://www.amazon.com/ap/oa?")
        assert "client_id=test_client_id" in url
        assert "response_type=code" in url
        assert "redirect_uri=" in url
        assert "scope=" in url

    def test_includes_smapi_scope(self, client, const):
        url = client.get_authorization_url("https://example.com/callback", const.SCOPE_SMAPI)
        assert "alexa%3A%3Aask%3Askills%3Areadwrite" in url
        assert "alexa%3A%3Aask%3Amodels%3Areadwrite" in url


# ---------------------------------------------------------------------------
# Test: async_exchange_code
# ---------------------------------------------------------------------------


class TestExchangeCode:

    @pytest.mark.asyncio
    async def test_success(self, client, const, api):
        token_response = {
            "access_token": "Atza|test_token",
            "refresh_token": "Atzr|test_refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        }
        mock_session = _make_mock_session(_make_mock_response(token_response))

        with patch.object(client, "_session", mock_session):
            result = await client.async_exchange_code(
                code="test_auth_code",
                redirect_uri="https://localhost:8123/auth/alexa_proactive/callback",
                scope=const.SCOPE_SMAPI,
            )

        call_args = mock_session.post.call_args
        assert call_args[0][0] == const.LWA_TOKEN_URL

        form_data = call_args[1]["data"]
        assert form_data["grant_type"] == "authorization_code"
        assert form_data["code"] == "test_auth_code"
        assert form_data["client_id"] == "test_client_id"
        assert form_data["client_secret"] == "test_client_secret"

        assert result["access_token"] == "Atza|test_token"
        assert const.SCOPE_SMAPI in client._tokens
        assert client._tokens[const.SCOPE_SMAPI].token == "Atza|test_token"
        assert client._refresh_tokens[const.SCOPE_SMAPI] == "Atzr|test_refresh"

    @pytest.mark.asyncio
    async def test_error_response(self, client, const, ha_error):
        mock_session = _make_mock_session(
            _make_mock_response({"error": "invalid_grant"})
        )

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(ha_error, match="LWA error"),
        ):
            await client.async_exchange_code(
                code="bad_code",
                redirect_uri="https://localhost:8123/auth/alexa_proactive/callback",
                scope=const.SCOPE_SMAPI,
            )

    @pytest.mark.asyncio
    async def test_network_error(self, client, const, ha_error):
        import aiohttp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
        mock_session.closed = False

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(ha_error, match="Cannot connect"),
        ):
            await client.async_exchange_code(
                code="test_code",
                redirect_uri="https://localhost:8123/auth/alexa_proactive/callback",
                scope=const.SCOPE_SMAPI,
            )

    @pytest.mark.asyncio
    async def test_unexpected_response(self, client, const, ha_error):
        mock_session = _make_mock_session(
            _make_mock_response({"unexpected": "data"})
        )

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(ha_error, match="Invalid LWA token response"),
        ):
            await client.async_exchange_code(
                code="test_code",
                redirect_uri="https://localhost:8123/auth/alexa_proactive/callback",
                scope=const.SCOPE_SMAPI,
            )


# ---------------------------------------------------------------------------
# Test: token retrieval and refresh
# ---------------------------------------------------------------------------


class TestGetToken:

    @pytest.mark.asyncio
    async def test_returns_cached_proactive_token(self, client_with_refresh, const, api):
        entry = api._TokenCache(token="Atza|cached", expires_at=time.monotonic() + 3000)
        client_with_refresh._tokens[const.SCOPE_PROACTIVE] = entry

        token = await client_with_refresh.async_get_proactive_token()
        assert token == "Atza|cached"

    @pytest.mark.asyncio
    async def test_returns_cached_smapi_token(self, client_with_refresh, const, api):
        entry = api._TokenCache(token="Atza|cached_smapi", expires_at=time.monotonic() + 3000)
        client_with_refresh._tokens[const.SCOPE_SMAPI] = entry

        token = await client_with_refresh.async_get_smapi_token()
        assert token == "Atza|cached_smapi"

    @pytest.mark.asyncio
    async def test_uses_client_credentials_when_expired(self, client, const, api):
        cc_response = {
            "access_token": "Atza|fresh",
            "expires_in": 3600,
            "token_type": "bearer",
        }
        mock_session = _make_mock_session(_make_mock_response(cc_response))

        with patch.object(client, "_session", mock_session):
            token = await client.async_get_proactive_token()

        assert token == "Atza|fresh"

        form_data = mock_session.post.call_args[1]["data"]
        assert form_data["grant_type"] == "client_credentials"
        assert form_data["scope"] == const.SCOPE_PROACTIVE

    @pytest.mark.asyncio
    async def test_client_credentials_error_raises(self, client, const, api, ha_error):
        mock_session = _make_mock_session(
            _make_mock_response({"error": "invalid_grant"})
        )

        with (
            patch.object(client, "_session", mock_session),
            pytest.raises(ha_error, match="LWA error: invalid_grant"),
        ):
            await client.async_get_proactive_token()

    @pytest.mark.asyncio
    async def test_client_credentials_stores_token(self, client, const, api):
        cc_response = {
            "access_token": "Atza|cc_token",
            "expires_in": 3600,
        }
        mock_session = _make_mock_session(_make_mock_response(cc_response))

        with patch.object(client, "_session", mock_session):
            await client.async_get_proactive_token()

        assert client._tokens[const.SCOPE_PROACTIVE].token == "Atza|cc_token"
