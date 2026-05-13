"""Shared test fixtures and Home Assistant module mocking."""

import sys
from unittest.mock import MagicMock

import pytest

# Single shared HomeAssistantError so all tests and loaded modules
# reference the same class, regardless of collection order.
_HomeAssistantError = type("HomeAssistantError", (Exception,), {})
_ServiceValidationError = type("ServiceValidationError", (_HomeAssistantError,), {})

# ---------------------------------------------------------------------------
# Mock homeassistant before any component modules are imported.
# This runs once at collection time, before test_api.py or test_smapi.py
# execute their own module-level setup.
# ---------------------------------------------------------------------------
_ha_pkg = MagicMock()
sys.modules.setdefault("homeassistant", _ha_pkg)
sys.modules.setdefault("homeassistant.core", MagicMock())

_exc_mod = sys.modules.get("homeassistant.exceptions")
if _exc_mod is None:
    _exc_mod = MagicMock()
    sys.modules["homeassistant.exceptions"] = _exc_mod
_exc_mod.HomeAssistantError = _HomeAssistantError
_exc_mod.ServiceValidationError = _ServiceValidationError

sys.modules.setdefault("homeassistant.helpers", MagicMock())
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", MagicMock())
sys.modules.setdefault("homeassistant.helpers.selector", MagicMock())
sys.modules.setdefault("homeassistant.helpers.network", MagicMock())

_json_mod = sys.modules.setdefault("homeassistant.helpers.json", MagicMock())
_json_mod.json_bytes = lambda obj: __import__("json").dumps(obj).encode()

# Mock homeassistant.components.http with a real-ish HomeAssistantView base.
# The view's .json() method must return an aiohttp-like Response with a .body.
from aiohttp import web as _aiohttp_web


class _FakeHomeAssistantView:
    requires_auth = True
    cors_allowed = False

    def __init__(self, hass=None):
        self._hass = hass

    def json(self, data):
        import json
        resp = MagicMock()
        resp.body = json.dumps(data).encode()
        return resp


_http_mod = sys.modules.setdefault("homeassistant.components.http", MagicMock())
_http_mod.HomeAssistantView = _FakeHomeAssistantView
_ha_pkg.components = MagicMock()
_ha_pkg.components.http = _http_mod
sys.modules.setdefault("homeassistant.data_entry_flow", MagicMock())
_const_mod = sys.modules.setdefault("homeassistant.const", MagicMock())
_const_mod.CONF_CLIENT_ID = "client_id"
_const_mod.CONF_CLIENT_SECRET = "client_secret"
_ha_pkg.const = _const_mod


# Provide a minimal real ConfigFlow base class so config_flow.py can
# inherit from it and tests can instantiate actual flow objects.
class _FakeConfigFlow:
    VERSION = 1

    def __init_subclass__(cls, **kwargs):
        pass

    def __init__(self):
        self.hass = None
        self._async_abort_entries_match = MagicMock()
        self._abort_if_unique_id_configured = MagicMock()

    async def async_set_unique_id(self, *a, **kw):
        pass

    def async_show_form(self, *, step_id, data_schema=None, errors=None, **kw):
        return {"type": "form", "step_id": step_id}

    def async_create_entry(self, *, title, data, **kw):
        return {"type": "create_entry", "title": title, "data": data}


_ce_mod = sys.modules.get("homeassistant.config_entries")
if _ce_mod is None:
    _ce_mod = MagicMock()
    sys.modules["homeassistant.config_entries"] = _ce_mod
_ce_mod.ConfigFlow = _FakeConfigFlow


class _ConfigEntryState:
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    SETUP_IN_PROGRESS = "setup_in_progress"
    SETUP_RETRY = "setup_retry"


_ce_mod.ConfigEntryState = _ConfigEntryState
# Ensure `from homeassistant import config_entries` resolves
_ha_pkg.config_entries = _ce_mod


@pytest.fixture
def ha_error():
    return _HomeAssistantError
