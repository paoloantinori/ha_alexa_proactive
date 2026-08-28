"""Integration tests for config entry lifecycle (setup/unload)."""
from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.alexa_proactive.const import DOMAIN, SERVICE_SEND
from custom_components.alexa_proactive.proactive import ProactiveClient

from .conftest import MOCK_ACCESS_TOKEN


async def test_setup_registers_service_and_entry(hass_with_http, mock_config_entry, aioclient_mock):
    """async_setup registers service; async_setup_entry sets up runtime_data."""
    hass = hass_with_http
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json={"access_token": MOCK_ACCESS_TOKEN, "expires_in": 3600, "token_type": "bearer"},
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Service registered by async_setup
    assert hass.services.has_service(DOMAIN, SERVICE_SEND)
    # runtime_data set by async_setup_entry
    assert hasattr(mock_config_entry, "runtime_data")
    assert mock_config_entry.runtime_data is not None
    assert isinstance(mock_config_entry.runtime_data, ProactiveClient)
    # hass.data populated
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_unload_clears_runtime_data(setup_entry):
    """async_unload_entry deletes runtime_data and clears hass.data."""
    hass, entry = setup_entry
    assert entry.state.value == "loaded"

    result = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert result
    # HA deletes runtime_data on successful unload
    assert not hasattr(entry, "runtime_data")
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_service_callable_after_setup(setup_entry, aioclient_mock):
    """Service call succeeds when entry is loaded."""
    hass, _entry = setup_entry

    # Mock proactive events API for the service call
    aioclient_mock.post(
        "https://api.eu.amazonalexa.com/v1/proactiveEvents/stages/development",
        json={},
        status=200,
    )

    await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
    await hass.async_block_till_done()


async def test_service_raises_after_unload(setup_entry):
    """Service call raises ServiceValidationError after unload."""
    hass, entry = setup_entry

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
