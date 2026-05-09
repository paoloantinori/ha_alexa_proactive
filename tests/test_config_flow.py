"""Unit tests for the config flow (config_flow.py)."""
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


def _load_models():
    return _load_submodule("alexa_proactive.models", "models.py")


def _load_api():
    _load_const()
    return _load_submodule("alexa_proactive.api", "api.py")


def _load_smapi():
    _load_api()
    return _load_submodule("alexa_proactive.smapi", "smapi.py")


def _load_config_flow():
    _load_const()
    _load_models()
    _load_api()
    _load_smapi()
    # Force reload to pick up conftest's _FakeConfigFlow base class
    mod_name = "alexa_proactive.config_flow"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return _load_submodule(mod_name, "config_flow.py")


# ---------------------------------------------------------------------------
# Mock HA infrastructure for config flow tests
# ---------------------------------------------------------------------------


def _make_hass():
    """Create a minimal mock hass for config flow tests."""
    hass = MagicMock()

    # config_entries.flow support
    flow_mgr = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.flow = flow_mgr
    hass.config_entries.async_entries = MagicMock(return_value=[])

    return hass


def _make_flow(hass, ha_error):
    """Create a config flow instance bound to mock hass."""
    config_flow_mod = _load_config_flow()
    flow = config_flow_mod.AlexaProactiveConfigFlow()
    flow.hass = hass
    flow._async_abort_entries_match = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


# ---------------------------------------------------------------------------
# Shared test data and helpers
# ---------------------------------------------------------------------------

_USER_INPUT = {
    "client_id": "test_id",
    "client_secret": "test_secret",
    "region": "eu",
}

_SETUP_RESULT = {
    "skill_id": "amzn1.ask.skill.123",
    "vendor_id": "VENDOR123",
    "webhook_url": "https://example.com/api/alexa_proactive",
}


def _set_flow_credentials(flow):
    """Set the credential attributes that tests need on a flow instance."""
    flow._client_id = _USER_INPUT["client_id"]
    flow._client_secret = _USER_INPUT["client_secret"]
    flow._region = _USER_INPUT["region"]


def _patch_lwa(autospec=True):
    """Return a patch context for LWAClient."""
    return patch("alexa_proactive.config_flow.LWAClient", autospec=autospec)


def _patch_smapi():
    """Return a patch context for SMTPClient."""
    return patch("alexa_proactive.config_flow.SMTPClient", autospec=True)


def _patch_get_url(url="https://example.com"):
    """Return a patch context for get_url."""
    return patch("alexa_proactive.config_flow.get_url", return_value=url)


def _extract_form_errors(flow):
    """Extract the errors dict from the last async_show_form call."""
    return flow.async_show_form.call_args[1]["errors"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config_flow_mod():
    return _load_config_flow()


@pytest.fixture(scope="module")
def const():
    return _load_const()


@pytest.fixture
def hass():
    return _make_hass()


@pytest.fixture
def flow(hass, ha_error):
    return _make_flow(hass, ha_error)


# ---------------------------------------------------------------------------
# Test: async_step_user
# ---------------------------------------------------------------------------


class TestStepUser:

    @pytest.mark.asyncio
    async def test_shows_form_on_no_input(self, flow):
        await flow.async_step_user(None)
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args
        assert call_kwargs[1]["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_valid_credentials_proceeds_to_setup(self, flow, ha_error):
        flow.async_step_setup = AsyncMock(return_value={"type": "form", "step_id": "setup"})
        with _patch_lwa() as mock_lwa_cls:
            mock_lwa = mock_lwa_cls.return_value
            mock_lwa.async_get_proactive_token = AsyncMock(return_value="token1")
            mock_lwa.async_get_smapi_token = AsyncMock(return_value="token2")

            await flow.async_step_user(_USER_INPUT)

        flow.async_set_unique_id.assert_called_once_with("test_id")
        flow._abort_if_unique_id_configured.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_credentials_shows_error(self, flow, ha_error):
        with _patch_lwa() as mock_lwa_cls:
            mock_lwa = mock_lwa_cls.return_value
            mock_lwa.async_get_proactive_token = AsyncMock(side_effect=ha_error("bad creds"))

            await flow.async_step_user(_USER_INPUT)

        assert _extract_form_errors(flow)["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_missing_smapi_scope_shows_error(self, flow, ha_error):
        with _patch_lwa() as mock_lwa_cls:
            mock_lwa = mock_lwa_cls.return_value
            mock_lwa.async_get_proactive_token = AsyncMock(return_value="token1")
            mock_lwa.async_get_smapi_token = AsyncMock(side_effect=ha_error("scope"))

            await flow.async_step_user(_USER_INPUT)

        assert _extract_form_errors(flow)["base"] == "scope_missing"

    @pytest.mark.asyncio
    async def test_schema_has_region_field(self, flow, config_flow_mod):
        schema = config_flow_mod._USER_SCHEMA
        assert "region" in schema.schema


# ---------------------------------------------------------------------------
# Test: async_step_setup
# ---------------------------------------------------------------------------


class TestStepSetup:

    @pytest.mark.asyncio
    async def test_setup_creates_skill_and_proceeds(self, flow, ha_error):
        _set_flow_credentials(flow)

        with (
            _patch_get_url(),
            _patch_lwa(),
            _patch_smapi() as mock_smapi_cls,
        ):
            mock_smapi = mock_smapi_cls.return_value
            mock_smapi.async_setup_skill_complete = AsyncMock(return_value=_SETUP_RESULT)

            await flow.async_step_setup(None)

        assert flow._setup_result == _SETUP_RESULT

    @pytest.mark.asyncio
    async def test_setup_smapi_error_shows_error(self, flow, ha_error):
        _set_flow_credentials(flow)

        with (
            _patch_get_url(),
            _patch_lwa(),
            _patch_smapi() as mock_smapi_cls,
        ):
            mock_smapi = mock_smapi_cls.return_value
            mock_smapi.async_setup_skill_complete = AsyncMock(side_effect=ha_error("SMAPI failed"))

            await flow.async_step_setup(None)

        assert _extract_form_errors(flow)["base"] == "smapi_error"


# ---------------------------------------------------------------------------
# Test: async_step_finish
# ---------------------------------------------------------------------------


class TestStepFinish:

    @pytest.mark.asyncio
    async def test_shows_form_when_no_input(self, flow):
        flow._setup_result = _SETUP_RESULT
        await flow.async_step_finish(None)
        flow.async_show_form.assert_called_once()
        assert flow.async_show_form.call_args[1]["step_id"] == "finish"

    @pytest.mark.asyncio
    async def test_finish_creates_entry(self, flow):
        _set_flow_credentials(flow)
        flow._setup_result = _SETUP_RESULT

        await flow.async_step_finish({"confirm": True})

        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args
        assert call_kwargs[1]["title"] == "Alexa Proactive Events"
        data = call_kwargs[1]["data"]
        assert data["client_id"] == "test_id"
        assert data["client_secret"] == "test_secret"
        assert data["region"] == "eu"
        assert data["skill_id"] == "amzn1.ask.skill.123"
        assert data["vendor_id"] == "VENDOR123"
        assert data["webhook_url"] == "https://example.com/api/alexa_proactive"


# ---------------------------------------------------------------------------
# Test: webhook URL generation
# ---------------------------------------------------------------------------


class TestWebhookUrl:

    @pytest.mark.asyncio
    async def test_webhook_url_uses_external_url(self, flow, ha_error):
        _set_flow_credentials(flow)

        with (
            _patch_get_url("https://my-ha.duckdns.org:8123"),
            _patch_lwa(),
            _patch_smapi() as mock_smapi_cls,
        ):
            mock_smapi = mock_smapi_cls.return_value
            mock_smapi.async_setup_skill_complete = AsyncMock(
                return_value={
                    "skill_id": "skill1",
                    "vendor_id": "vendor1",
                    "webhook_url": "https://my-ha.duckdns.org:8123/api/alexa_proactive",
                }
            )
            await flow.async_step_setup(None)

        call_args = mock_smapi.async_setup_skill_complete.call_args
        assert call_args[1]["webhook_url"] == "https://my-ha.duckdns.org:8123/api/alexa_proactive"
