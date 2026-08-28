"""Integration tests for the alexa_proactive.send service."""
from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.alexa_proactive.const import (
    CONF_ALEXA_USER_ID,
    DOMAIN,
    SERVICE_SEND,
)

PROACTIVE_URL = "https://api.eu.amazonalexa.com/v1/proactiveEvents/stages/development"
LWA_URL = "https://api.amazon.com/auth/O2/token"


def _get_proactive_payload(aioclient_mock):
    """Extract the last proactive events payload dict."""
    for call in reversed(aioclient_mock.mock_calls):
        if call[0] == "POST" and "proactiveEvents" in str(call[1]):
            return call[2]
    raise AssertionError("No proactive events call found")


async def test_send_default_params(setup_entry, aioclient_mock):
    """Service call with defaults hits LWA token + Proactive Events API."""
    hass, _entry = setup_entry

    aioclient_mock.post(PROACTIVE_URL, json={}, status=200)

    await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
    await hass.async_block_till_done()

    calls = [str(c) for c in aioclient_mock.mock_calls]
    assert any("api.amazon.com" in c for c in calls)
    assert any("proactiveEvents" in c for c in calls)


async def test_send_custom_sender_and_count(setup_entry, aioclient_mock):
    """Service call passes sender and count to the proactive payload."""
    hass, _entry = setup_entry

    aioclient_mock.post(PROACTIVE_URL, json={}, status=200)

    await hass.services.async_call(
        DOMAIN, SERVICE_SEND, {"sender": "Kitchen", "count": 5}, blocking=True
    )
    await hass.async_block_till_done()

    payload = _get_proactive_payload(aioclient_mock)
    assert payload["event"]["payload"]["messageGroup"]["creator"]["name"] == "Kitchen"
    assert payload["event"]["payload"]["messageGroup"]["count"] == 5


async def test_send_payload_structure(setup_entry, aioclient_mock):
    """Payload has required Proactive Events API fields."""
    hass, _entry = setup_entry

    aioclient_mock.post(PROACTIVE_URL, json={}, status=200)

    await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
    await hass.async_block_till_done()

    payload = _get_proactive_payload(aioclient_mock)

    assert "timestamp" in payload
    assert "referenceId" in payload
    assert "expiryTime" in payload
    assert payload["event"]["name"] == "AMAZON.MessageAlert.Activated"


async def test_send_unicast_with_user_id(setup_entry, aioclient_mock):
    """Payload uses Unicast when alexa_user_id is present in entry.data."""
    hass, _entry = setup_entry

    aioclient_mock.post(PROACTIVE_URL, json={}, status=200)

    # Simulate persisted user ID capture (AlexaProactiveView writes it here)
    hass.config_entries.async_update_entry(
        _entry, data={**_entry.data, CONF_ALEXA_USER_ID: "amzn1.ask.user.test"}
    )

    await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
    await hass.async_block_till_done()

    payload = _get_proactive_payload(aioclient_mock)
    assert payload["relevantAudience"]["type"] == "Unicast"
    assert payload["relevantAudience"]["payload"]["user"] == "amzn1.ask.user.test"


async def test_send_multicast_without_user_id(setup_entry, aioclient_mock):
    """Payload uses Multicast when no alexa_user_id."""
    hass, _entry = setup_entry

    aioclient_mock.post(PROACTIVE_URL, json={}, status=200)

    await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
    await hass.async_block_till_done()

    payload = _get_proactive_payload(aioclient_mock)
    assert payload["relevantAudience"]["type"] == "Multicast"


async def test_send_retry_on_403(setup_entry, aioclient_mock, caplog):
    """Service retries with a fresh token on 403."""
    hass, _entry = setup_entry

    # Register 403 for proactive URL — retry will also hit 403 and propagate,
    # but we verify the retry log message appears
    aioclient_mock.post(PROACTIVE_URL, status=403, json={})

    import logging
    with caplog.at_level(logging.DEBUG, logger="custom_components.alexa_proactive.proactive"):
        with pytest.raises(Exception):
            await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
        await hass.async_block_till_done()

    assert "Retrying with fresh token" in caplog.text


async def test_send_error_no_config_entry(hass_with_http):
    """Service raises ServiceValidationError when no entry is loaded."""
    hass = hass_with_http

    from custom_components.alexa_proactive import async_setup
    await async_setup(hass, {})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, SERVICE_SEND, {}, blocking=True)
