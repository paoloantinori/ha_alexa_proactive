"""Shared test fixtures and Home Assistant module mocking."""

import sys
from unittest.mock import MagicMock

import pytest

# Single shared HomeAssistantError so all tests and loaded modules
# reference the same class, regardless of collection order.
_HomeAssistantError = type("HomeAssistantError", (Exception,), {})

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

sys.modules.setdefault("homeassistant.helpers", MagicMock())
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", MagicMock())


@pytest.fixture
def ha_error():
    return _HomeAssistantError
