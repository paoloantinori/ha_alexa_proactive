"""Unit tests for the integration __init__.py (service wiring)."""
from __future__ import annotations

import importlib.util
import sys
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


def _load_init():
    _register_package("alexa_proactive")
    mod_name = "alexa_proactive"
    if mod_name in sys.modules:
        existing = sys.modules[mod_name]
        # Force reload to pick up latest changes
        if hasattr(existing, "async_setup_entry"):
            return existing
    spec = importlib.util.spec_from_file_location(
        mod_name, COMPONENT_DIR / "__init__.py", submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    mod.__path__ = [str(COMPONENT_DIR)]
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_hass():
    hass = MagicMock()
    hass.data = {"alexa_proactive": {"test_entry": {"alexa_user_id": "amzn1.ask.user.test"}}}
    hass.services = MagicMock()
    hass.http = MagicMock()

    # Mock config_entries
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.state = "loaded"
    entry.data = {
        "client_id": "test_id",
        "client_secret": "test_secret",
        "region": "eu",
        "skill_id": "skill123",
        "vendor_id": "vendor123",
        "refresh_token": "Atzr|test_refresh",
        "skill_client_id": "amzn1.application-oa2-client.skill123",
        "skill_client_secret": "skill_secret_456",
    }
    entry.runtime_data = None

    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    return hass, entry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def init_mod():
    return _load_init()


@pytest.fixture
def hass_entry():
    return _make_hass()


@pytest.fixture
def hass(hass_entry):
    return hass_entry[0]


@pytest.fixture
def entry(hass_entry):
    return hass_entry[1]


# ---------------------------------------------------------------------------
# Test: async_setup
# ---------------------------------------------------------------------------


class TestAsyncSetup:

    @pytest.mark.asyncio
    async def test_registers_service(self, init_mod, hass):
        await init_mod.async_setup(hass, {})
        hass.services.async_register.assert_called_once()
        args = hass.services.async_register.call_args
        assert args[0][0] == "alexa_proactive"
        assert args[0][1] == "send"

    @pytest.mark.asyncio
    async def test_returns_true(self, init_mod, hass):
        result = await init_mod.async_setup(hass, {})
        assert result is True


# ---------------------------------------------------------------------------
# Test: service handler
# ---------------------------------------------------------------------------


class TestServiceHandler:

    @pytest.mark.asyncio
    async def test_service_sends_notification(self, init_mod, hass, entry):
        mock_client = MagicMock()
        mock_client.async_send = AsyncMock(return_value={})
        entry.runtime_data = mock_client

        await init_mod.async_setup(hass, {})
        handler = hass.services.async_register.call_args[0][2]

        call = MagicMock()
        call.data = {"sender": "Test Sender", "count": 3}
        await handler(call)

        mock_client.async_send.assert_called_once_with(
            sender="Test Sender", count=3, user_id="amzn1.ask.user.test"
        )

    @pytest.mark.asyncio
    async def test_service_uses_defaults(self, init_mod, hass, entry):
        mock_client = MagicMock()
        mock_client.async_send = AsyncMock(return_value={})
        entry.runtime_data = mock_client

        await init_mod.async_setup(hass, {})
        handler = hass.services.async_register.call_args[0][2]

        call = MagicMock()
        call.data = {}
        await handler(call)

        mock_client.async_send.assert_called_once_with(
            sender="Home Assistant", count=1, user_id="amzn1.ask.user.test"
        )

    @pytest.mark.asyncio
    async def test_service_raises_when_no_loaded_entry(self, init_mod, hass, ha_error):
        hass.config_entries.async_entries = MagicMock(return_value=[])
        await init_mod.async_setup(hass, {})
        handler = hass.services.async_register.call_args[0][2]

        call = MagicMock()
        call.data = {}

        with pytest.raises(Exception) as exc_info:
            await handler(call)
        assert "not configured" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_service_raises_when_no_runtime_data(self, init_mod, hass, entry):
        entry.runtime_data = None
        await init_mod.async_setup(hass, {})
        handler = hass.services.async_register.call_args[0][2]

        call = MagicMock()
        call.data = {}

        with pytest.raises(Exception) as exc_info:
            await handler(call)
        assert "not fully initialized" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test: async_setup_entry
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:

    @pytest.mark.asyncio
    async def test_registers_http_view(self, init_mod, hass, entry):
        with patch("alexa_proactive.LWAClient"), patch("alexa_proactive.ProactiveClient"):
            await init_mod.async_setup_entry(hass, entry)
        hass.http.register_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_runtime_data(self, init_mod, hass, entry):
        with patch("alexa_proactive.LWAClient"), patch("alexa_proactive.ProactiveClient") as mock_pc:
            await init_mod.async_setup_entry(hass, entry)
        assert entry.runtime_data is mock_pc.return_value

    @pytest.mark.asyncio
    async def test_initializes_hass_data(self, init_mod, hass, entry):
        with patch("alexa_proactive.LWAClient"), patch("alexa_proactive.ProactiveClient"):
            await init_mod.async_setup_entry(hass, entry)
        assert "alexa_proactive" in hass.data
        assert "test_entry" in hass.data["alexa_proactive"]

    @pytest.mark.asyncio
    async def test_returns_true(self, init_mod, hass, entry):
        with patch("alexa_proactive.LWAClient"), patch("alexa_proactive.ProactiveClient"):
            result = await init_mod.async_setup_entry(hass, entry)
        assert result is True


# ---------------------------------------------------------------------------
# Test: async_unload_entry
# ---------------------------------------------------------------------------


class TestAsyncUnloadEntry:

    @pytest.mark.asyncio
    async def test_clears_runtime_data(self, init_mod, hass, entry):
        entry.runtime_data = MagicMock()
        await init_mod.async_unload_entry(hass, entry)
        assert entry.runtime_data is None

    @pytest.mark.asyncio
    async def test_cleans_up_hass_data(self, init_mod, hass, entry):
        hass.data["alexa_proactive"] = {"test_entry": {}}
        await init_mod.async_unload_entry(hass, entry)
        assert "test_entry" not in hass.data.get("alexa_proactive", {})

    @pytest.mark.asyncio
    async def test_returns_true(self, init_mod, hass, entry):
        result = await init_mod.async_unload_entry(hass, entry)
        assert result is True
