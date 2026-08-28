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
    mod_name = "alexa_proactive.config_flow"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return _load_submodule(mod_name, "config_flow.py")


# ---------------------------------------------------------------------------
# Mock HA infrastructure
# ---------------------------------------------------------------------------


def _make_hass():
    hass = MagicMock()
    flow_mgr = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.flow = flow_mgr
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.data = {}
    return hass


def _make_flow(hass, ha_error):
    config_flow_mod = _load_config_flow()
    flow = config_flow_mod.AlexaProactiveConfigFlow()
    flow.hass = hass
    flow.flow_id = "test_flow_id_123"
    flow._async_abort_entries_match = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_USER_INPUT = {
    "client_id": "test_id",
    "client_secret": "test_secret",
    "region": "eu",
    "invocation_name": "ping me",
}

_TOKEN_RESULT = {
    "access_token": "Atza|test_access",
    "refresh_token": "Atzr|test_refresh",
    "expires_in": 3600,
    "token_type": "bearer",
}

_SETUP_RESULT = {
    "skill_id": "amzn1.ask.skill.123",
    "vendor_id": "VENDOR123",
    "webhook_url": "https://example.com/api/alexa_proactive",
}


def _set_flow_credentials(flow):
    flow._client_id = _USER_INPUT["client_id"]
    flow._client_secret = _USER_INPUT["client_secret"]
    flow._region = _USER_INPUT["region"]
    flow._invocation_name = _USER_INPUT["invocation_name"]


def _patch_lwa(autospec=True):
    return patch("alexa_proactive.config_flow.LWAClient", autospec=autospec)


def _patch_smapi():
    return patch("alexa_proactive.config_flow.SMTPClient", autospec=True)


def _patch_get_url(url="https://example.com"):
    return patch("homeassistant.helpers.network.get_url", return_value=url)


def _extract_form_errors(flow):
    return flow.async_show_form.call_args[1]["errors"]


def _extract_placeholders(flow):
    return flow.async_show_form.call_args[1].get("description_placeholders", {})


def _store_auth_code(hass, flow_id, suffix, code):
    """Simulate the callback view storing an auth code."""
    const = _load_const()
    hass.data.setdefault(const.DOMAIN, {}).setdefault("auth_codes", {})[f"{flow_id}_{suffix}"] = code


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
    async def test_valid_input_proceeds_to_auth_smapi(self, flow, ha_error):
        flow.async_step_auth_smapi = AsyncMock(return_value={"type": "form", "step_id": "auth_smapi"})

        await flow.async_step_user(_USER_INPUT)

        flow.async_set_unique_id.assert_called_once_with("test_id")
        flow._abort_if_unique_id_configured.assert_called_once()
        flow.async_step_auth_smapi.assert_called_once()

    @pytest.mark.asyncio
    async def test_digit_start_invocation_name_shows_error(self, flow, ha_error):
        flow.async_step_auth_smapi = AsyncMock()

        await flow.async_step_user({**_USER_INPUT, "invocation_name": "4 notifications"})

        flow.async_show_form.assert_called_once()
        assert _extract_form_errors(flow) == {"invocation_name": "invalid_invocation_name"}
        flow.async_set_unique_id.assert_not_called()
        flow.async_step_auth_smapi.assert_not_called()

    @pytest.mark.asyncio
    async def test_uppercase_invocation_name_is_normalized(self, flow, ha_error):
        flow.async_step_auth_smapi = AsyncMock(return_value={"type": "form", "step_id": "auth_smapi"})

        await flow.async_step_user({**_USER_INPUT, "invocation_name": "  HomeAssistant   Notifier "})

        assert flow._invocation_name == "homeassistant notifier"
        flow.async_step_auth_smapi.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_has_region_field(self, flow):
        await flow.async_step_user(None)
        schema = flow.async_show_form.call_args[1]["data_schema"]
        assert "region" in schema.schema

    @pytest.mark.asyncio
    async def test_schema_has_invocation_name_field(self, flow):
        await flow.async_step_user(None)
        schema = flow.async_show_form.call_args[1]["data_schema"]
        assert "invocation_name" in schema.schema

    @pytest.mark.asyncio
    async def test_schema_has_locales_field(self, flow):
        await flow.async_step_user(None)
        schema = flow.async_show_form.call_args[1]["data_schema"]
        assert "locales" in schema.schema


# ---------------------------------------------------------------------------
# Test: async_step_auth_smapi
# ---------------------------------------------------------------------------


class TestStepAuthSmapi:

    @pytest.mark.asyncio
    async def test_shows_auth_url_on_first_call(self, flow):
        _set_flow_credentials(flow)
        mock_lwa = MagicMock()
        mock_lwa.get_authorization_url = MagicMock(
            return_value="https://www.amazon.com/ap/oa?client_id=test_id"
        )
        flow._lwa_client = mock_lwa

        with _patch_get_url("https://my-ha.example.com"):
            await flow.async_step_auth_smapi(None)

        placeholders = _extract_placeholders(flow)
        assert "auth_url" in placeholders
        assert "amazon.com" in placeholders["auth_url"]

    @pytest.mark.asyncio
    async def test_code_exchange_proceeds_to_setup(self, flow, hass):
        _set_flow_credentials(flow)
        flow.async_step_setup = AsyncMock(return_value={"type": "form", "step_id": "setup"})

        mock_lwa = MagicMock()
        mock_lwa.async_exchange_code = AsyncMock(return_value=_TOKEN_RESULT)
        flow._lwa_client = mock_lwa

        _store_auth_code(hass, flow.flow_id, "smapi", "test_smapi_code")

        with _patch_get_url():
            await flow.async_step_auth_smapi({"submit": True})

        mock_lwa.async_exchange_code.assert_called_once()
        flow.async_step_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_code_shows_pending_error(self, flow):
        _set_flow_credentials(flow)
        mock_lwa = MagicMock()
        mock_lwa.get_authorization_url = MagicMock(return_value="https://www.amazon.com/ap/oa?...")
        flow._lwa_client = mock_lwa

        with _patch_get_url():
            await flow.async_step_auth_smapi({"submit": True})

        assert _extract_form_errors(flow)["base"] == "authorization_pending"

    @pytest.mark.asyncio
    async def test_invalid_code_shows_error(self, flow, hass, ha_error):
        _set_flow_credentials(flow)
        _store_auth_code(hass, flow.flow_id, "smapi", "bad_code")

        mock_lwa = MagicMock()
        mock_lwa.async_exchange_code = AsyncMock(
            side_effect=ha_error("LWA error: invalid_grant")
        )
        mock_lwa.get_authorization_url = MagicMock(return_value="https://www.amazon.com/ap/oa?...")
        flow._lwa_client = mock_lwa

        with _patch_get_url():
            await flow.async_step_auth_smapi({"submit": True})

        assert _extract_form_errors(flow)["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_no_lwa_client_redirects_to_user(self, flow):
        flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})
        result = await flow.async_step_auth_smapi(None)
        flow.async_step_user.assert_called_once()


# ---------------------------------------------------------------------------
# Test: async_step_setup
# ---------------------------------------------------------------------------


class TestStepSetup:

    @pytest.mark.asyncio
    async def test_setup_creates_skill_and_proceeds(self, flow, hass):
        _set_flow_credentials(flow)

        mock_lwa = MagicMock()
        flow._lwa_client = mock_lwa

        with (
            _patch_get_url(),
            _patch_smapi() as mock_smapi_cls,
        ):
            mock_smapi = mock_smapi_cls.return_value
            mock_smapi.async_setup_skill_complete = AsyncMock(return_value=_SETUP_RESULT)

            await flow.async_step_setup(None)

        assert flow._setup_result == _SETUP_RESULT

    @pytest.mark.asyncio
    async def test_setup_smapi_error_shows_error(self, flow, hass, ha_error):
        _set_flow_credentials(flow)

        mock_lwa = MagicMock()
        flow._lwa_client = mock_lwa

        with (
            _patch_get_url(),
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
    async def test_finish_creates_entry(self, flow, const):
        _set_flow_credentials(flow)
        flow._setup_result = _SETUP_RESULT

        mock_lwa = MagicMock()
        mock_lwa.get_refresh_token = MagicMock(return_value="Atzr|smapi_refresh")
        flow._lwa_client = mock_lwa

        await flow.async_step_finish({"confirm": True})

        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args
        assert call_kwargs[1]["title"] == "Alexa Proactive Events"
        data = call_kwargs[1]["data"]
        assert data["client_id"] == "test_id"
        assert data["client_secret"] == "test_secret"
        assert data["region"] == "eu"
        assert data["invocation_name"] == "ping me"
        assert data["skill_id"] == "amzn1.ask.skill.123"
        assert data["vendor_id"] == "VENDOR123"
        assert data["webhook_url"] == "https://example.com/api/alexa_proactive"
        assert data["refresh_token"] == "Atzr|smapi_refresh"


# ---------------------------------------------------------------------------
# Test: webhook URL generation
# ---------------------------------------------------------------------------


class TestWebhookUrl:

    @pytest.mark.asyncio
    async def test_webhook_url_uses_external_url(self, flow):
        _set_flow_credentials(flow)

        mock_lwa = MagicMock()
        flow._lwa_client = mock_lwa

        with (
            _patch_get_url("https://my-ha.duckdns.org:8123"),
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


# ---------------------------------------------------------------------------
# Test: _get_suggested_locales
# ---------------------------------------------------------------------------


class TestGetSuggestedLocales:

    def test_detects_from_country(self, flow, hass):
        """Country IT maps to it-IT, returned first with en-US fallback."""
        hass.config.country = "IT"
        hass.config.language = "en"
        assert flow._get_suggested_locales() == ["it-IT", "en-US"]

    def test_detects_from_country_case_insensitive(self, flow, hass):
        """Lowercase country code is uppercased before lookup."""
        hass.config.country = "it"
        hass.config.language = "en"
        assert flow._get_suggested_locales() == ["it-IT", "en-US"]

    def test_falls_back_to_language(self, flow, hass):
        """When country has no mapping, language is used instead."""
        hass.config.country = "ZZ"
        hass.config.language = "de"
        assert flow._get_suggested_locales() == ["de-DE", "en-US"]

    def test_language_strips_region(self, flow, hass):
        """Language tag like 'de-AT' is split on '-' and only 'de' is used."""
        hass.config.country = None
        hass.config.language = "de-AT"
        assert flow._get_suggested_locales() == ["de-DE", "en-US"]

    def test_defaults_to_en_us(self, flow, hass):
        """No matching country or language returns only en-US."""
        hass.config.country = "ZZ"
        hass.config.language = "zz"
        assert flow._get_suggested_locales() == ["en-US"]

    def test_en_us_no_duplication(self, flow, hass):
        """When detected locale is already en-US, do not duplicate it."""
        hass.config.country = "US"
        hass.config.language = "en"
        assert flow._get_suggested_locales() == ["en-US"]

    def test_none_country_falls_through(self, flow, hass):
        """Country=None falls through to language detection."""
        hass.config.country = None
        hass.config.language = "ja"
        assert flow._get_suggested_locales() == ["ja-JP", "en-US"]

    def test_none_language_defaults(self, flow, hass):
        """Both country=None and language=None produce the default locale."""
        hass.config.country = None
        hass.config.language = None
        assert flow._get_suggested_locales() == ["en-US"]

    def test_unknown_country_unknown_language(self, flow, hass):
        """Unmapped country followed by unmapped language yields en-US."""
        hass.config.country = "XX"
        hass.config.language = "xx"
        assert flow._get_suggested_locales() == ["en-US"]


# ---------------------------------------------------------------------------
# Test: Options flow invocation name handling
# ---------------------------------------------------------------------------


class TestOptionsFlowInvocationName:

    def _make_entry(self):
        entry = MagicMock()
        entry.data = {
            "client_id": "test_id",
            "client_secret": "test_secret",
            "region": "eu",
            "invocation_name": "ping me",
            "locales": ["en-US"],
            "skill_id": "amzn1.ask.skill.123",
            "vendor_id": "VENDOR123",
            "webhook_url": "https://example.com/api/alexa_proactive",
            "refresh_token": "Atzr|test_refresh",
            "alexa_user_id": "amzn1.ask.user.persisted",
        }
        return entry

    def _make_options_flow(self, config_flow_mod, hass, entry):
        flow = config_flow_mod.AlexaProactiveOptionsFlow(entry)
        flow.hass = hass
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        return flow

    @pytest.mark.asyncio
    async def test_digit_start_rename_shows_error(self, config_flow_mod, hass, ha_error):
        entry = self._make_entry()
        flow = self._make_options_flow(config_flow_mod, hass, entry)

        with patch("alexa_proactive.config_flow.LWAClient") as mock_lwa:
            await flow.async_step_init({"invocation_name": "4 notifications"})

        flow.async_show_form.assert_called_once()
        assert _extract_form_errors(flow) == {"invocation_name": "invalid_invocation_name"}
        mock_lwa.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_legacy_name_is_noop(self, config_flow_mod, hass, ha_error):
        """A stored non-normalized legacy name, resubmitted unchanged, must not
        trigger a remote manifest PUT or an entry.data rewrite (C1)."""
        entry = self._make_entry()
        entry.data["invocation_name"] = "Ping Me"
        flow = self._make_options_flow(config_flow_mod, hass, entry)

        with patch("alexa_proactive.config_flow.LWAClient") as mock_lwa:
            await flow.async_step_init({"invocation_name": "Ping Me"})

        mock_lwa.assert_not_called()
        hass.config_entries.async_update_entry.assert_not_called()
        flow.async_create_entry.assert_called_once_with(
            title="", data={"invocation_name": "ping me"}
        )

    @pytest.mark.asyncio
    async def test_rename_upload_failure_shows_error(self, config_flow_mod, hass, ha_error):
        """When no interaction model uploads, the rename must not be recorded."""
        entry = self._make_entry()
        flow = self._make_options_flow(config_flow_mod, hass, entry)

        with (
            patch("alexa_proactive.config_flow.LWAClient") as mock_lwa_cls,
            patch("alexa_proactive.config_flow.SMTPClient", autospec=True) as mock_smapi_cls,
        ):
            mock_lwa_cls.return_value = MagicMock()
            mock_smapi_cls.return_value.async_upload_models = AsyncMock(return_value=[])
            await flow.async_step_init({"invocation_name": "notify me"})

        assert _extract_form_errors(flow) == {"base": "smapi_error"}
        hass.config_entries.async_update_entry.assert_not_called()
        flow.async_create_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_rename_normalizes_and_preserves_user_id(self, config_flow_mod, hass, ha_error):
        entry = self._make_entry()
        flow = self._make_options_flow(config_flow_mod, hass, entry)

        with (
            patch("alexa_proactive.config_flow.LWAClient") as mock_lwa_cls,
            patch("alexa_proactive.config_flow.SMTPClient", autospec=True) as mock_smapi_cls,
        ):
            mock_lwa_cls.return_value = MagicMock()
            await flow.async_step_init({"invocation_name": "  HomeAssistant Notifier "})

        mock_smapi_cls.return_value.async_update_manifest.assert_awaited_once_with(
            "amzn1.ask.skill.123", "https://example.com/api/alexa_proactive", "homeassistant notifier"
        )
        mock_smapi_cls.return_value.async_upload_models.assert_awaited_once_with(
            "amzn1.ask.skill.123", "homeassistant notifier", ["en-US"]
        )
        hass.config_entries.async_update_entry.assert_called_once()
        update_kwargs = hass.config_entries.async_update_entry.call_args[1]
        assert update_kwargs["data"]["invocation_name"] == "homeassistant notifier"
        assert update_kwargs["data"]["alexa_user_id"] == "amzn1.ask.user.persisted"
        flow.async_create_entry.assert_called_once_with(
            title="", data={"invocation_name": "homeassistant notifier"}
        )
