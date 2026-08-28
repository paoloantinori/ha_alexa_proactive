"""Integration test fixtures for alexa_proactive."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.setup import async_setup_component

# Import config_flow to register the ConfigFlow handler with HA's HANDLERS registry
import custom_components.alexa_proactive.config_flow  # noqa: F401

from custom_components.alexa_proactive.api import LWAClient
from custom_components.alexa_proactive.const import (
    CONF_ALEXA_USER_ID,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INVOCATION_NAME,
    CONF_LOCALES,
    CONF_REGION,
    CONF_REFRESH_TOKEN,
    CONF_SKILL_CLIENT_ID,
    CONF_SKILL_CLIENT_SECRET,
    CONF_SKILL_ID,
    CONF_VENDOR_ID,
    CONF_WEBHOOK_URL,
    DOMAIN,
    SERVICE_SEND,
)

# -- Shared test constants --
MOCK_CLIENT_ID = "amzn1.application-oa2-client.test_integration"
MOCK_CLIENT_SECRET = "amzn1.oa2-cs.v1.integration_test_secret"
MOCK_REGION = "eu"
MOCK_INVOCATION_NAME = "ping me"
MOCK_SKILL_ID = "amzn1.ask.skill.integration_test"
MOCK_SKILL_CLIENT_ID = "amzn1.application-oa2-client.skill_integration_test"
MOCK_SKILL_CLIENT_SECRET = "amzn1.oa2-cs.v1.skill_integration_test_secret"
MOCK_VENDOR_ID = "VENDOR_TEST"
MOCK_WEBHOOK_URL = "http://localhost:8123/api/alexa_proactive"
MOCK_REFRESH_TOKEN = "Atzr|integration_test_refresh"
MOCK_ACCESS_TOKEN = "Atza|integration_test_access"
MOCK_USER_ID = "amzn1.ask.user.integration_test"

MOCK_ENTRY_DATA = {
    CONF_CLIENT_ID: MOCK_CLIENT_ID,
    CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
    CONF_REGION: MOCK_REGION,
    CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
    CONF_LOCALES: ["en-US"],
    CONF_SKILL_ID: MOCK_SKILL_ID,
    CONF_VENDOR_ID: MOCK_VENDOR_ID,
    CONF_WEBHOOK_URL: MOCK_WEBHOOK_URL,
    CONF_REFRESH_TOKEN: MOCK_REFRESH_TOKEN,
    CONF_SKILL_CLIENT_ID: MOCK_SKILL_CLIENT_ID,
    CONF_SKILL_CLIENT_SECRET: MOCK_SKILL_CLIENT_SECRET,
}

LWA_TOKEN_RESPONSE = {
    "access_token": MOCK_ACCESS_TOKEN,
    "expires_in": 3600,
    "token_type": "bearer",
}

LWA_CODE_EXCHANGE_RESPONSE = {
    "access_token": "Atza|smapi_access",
    "refresh_token": "Atzr|smapi_refresh",
    "expires_in": 3600,
    "token_type": "bearer",
}

SMAPI_SETUP_RESULT = {
    "skill_id": MOCK_SKILL_ID,
    "vendor_id": MOCK_VENDOR_ID,
    "webhook_url": MOCK_WEBHOOK_URL,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom_components for all integration tests."""
    yield


@pytest.fixture(autouse=True)
def mock_component_sessions(hass, aioclient_mock):
    """Route the component's hand-made aiohttp sessions into aioclient_mock.

    LWAClient and ProactiveClient create their own ClientSession instead of
    using homeassistant.helpers.aiohttp_client, which is the only path the
    aioclient_mock fixture intercepts; without this patch every outbound call
    hits real DNS and the test plugin raises "DNS resolution disabled".
    """
    session = aioclient_mock.create_session(hass.loop)
    with patch.object(LWAClient, "_get_session", AsyncMock(return_value=session)):
        yield session


@pytest.fixture
async def hass_with_http(hass):
    """Provide a hass instance with http and persistent_notification set up."""
    await async_setup_component(hass, "http", {})
    await async_setup_component(hass, "persistent_notification", {})
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a MockConfigEntry with standard test data."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Alexa Proactive Events",
        data=MOCK_ENTRY_DATA,
        unique_id=MOCK_CLIENT_ID,
        version=1,
    )


@pytest.fixture
async def setup_entry(hass_with_http, mock_config_entry, aioclient_mock, mock_component_sessions):
    """Set up the integration config entry with mocked LWA outbound HTTP.

    Returns (hass, entry) after async_setup_entry completes.
    """
    hass = hass_with_http

    # Mock LWA client_credentials token endpoint
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json=LWA_TOKEN_RESPONSE,
    )

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Seed the ProactiveClient's hand-made session into the mocked one so
    # service calls hit aioclient_mock instead of real DNS.
    proactive = mock_config_entry.runtime_data
    if proactive is not None:
        proactive._session = mock_component_sessions

    return hass, mock_config_entry


@pytest.fixture
def mock_lwa_token(aioclient_mock):
    """Pre-mock the LWA token endpoint."""
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json=LWA_TOKEN_RESPONSE,
    )


@pytest.fixture
def mock_proactive_api(aioclient_mock):
    """Pre-mock the Proactive Events API endpoint (EU region)."""
    aioclient_mock.post(
        "https://api.eu.amazonalexa.com/v1/proactiveEvents/stages/development",
        json={},
        status=200,
    )
