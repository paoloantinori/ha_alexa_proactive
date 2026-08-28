"""Integration tests for the 4-step config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.alexa_proactive.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INVOCATION_NAME,
    CONF_LOCALES,
    CONF_REGION,
    CONF_SKILL_ID,
    CONF_VENDOR_ID,
    CONF_WEBHOOK_URL,
    DOMAIN,
)

from .conftest import (
    LWA_CODE_EXCHANGE_RESPONSE,
    MOCK_CLIENT_ID,
    MOCK_CLIENT_SECRET,
    MOCK_INVOCATION_NAME,
    MOCK_REGION,
    MOCK_SKILL_ID,
    MOCK_VENDOR_ID,
    MOCK_WEBHOOK_URL,
    SMAPI_SETUP_RESULT,
)


async def test_user_step_shows_form(hass_with_http):
    """Init flow shows the user credentials form."""
    result = await hass_with_http.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_abort_if_already_configured(hass_with_http, mock_config_entry):
    """Flow aborts when an entry with the same unique ID exists."""
    hass = hass_with_http
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    # Abort happens when credentials are submitted (unique_id check is on submit)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_auth_step_shows_auth_url(hass_with_http, aioclient_mock):
    """Submitting credentials advances to auth_smapi step with auth URL."""
    result = await hass_with_http.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass_with_http.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth_smapi"
    assert "auth_url" in result.get("description_placeholders", {})
    auth_url = result["description_placeholders"]["auth_url"]
    assert "amazon.com" in auth_url


async def test_auth_step_pending_when_no_code(hass_with_http):
    """Auth step shows authorization_pending error when no code is stored."""
    result = await hass_with_http.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass_with_http.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    flow_id = result["flow_id"]

    # Submit auth step without storing any code
    result = await hass_with_http.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "authorization_pending"


async def test_auth_step_invalid_code(hass_with_http, aioclient_mock):
    """Auth step shows invalid_auth when code exchange fails."""
    hass = hass_with_http

    # Mock LWA to return error on code exchange
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json={"error": "invalid_grant"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    flow_id = result["flow_id"]

    # Simulate callback storing a code
    lookup_key = f"{flow_id}_smapi"
    hass.data.setdefault(DOMAIN, {}).setdefault("auth_codes", {})[lookup_key] = "bad_code"

    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_setup_step_smapi_error(hass_with_http, aioclient_mock):
    """Setup step shows smapi_error when SMAPI call fails."""
    hass = hass_with_http

    # Mock LWA code exchange success
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json=LWA_CODE_EXCHANGE_RESPONSE,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    flow_id = result["flow_id"]

    # Simulate callback storing a valid code
    lookup_key = f"{flow_id}_smapi"
    hass.data.setdefault(DOMAIN, {}).setdefault("auth_codes", {})[lookup_key] = "valid_code"

    # Mock SMAPI to fail — patch SMTPClient to raise on setup
    with patch(
        "custom_components.alexa_proactive.config_flow.SMTPClient"
    ) as mock_smapi_cls:
        mock_smapi_cls.return_value.async_setup_skill_complete = AsyncMock(
            side_effect=Exception("SMAPI error")
        )
        from homeassistant.exceptions import HomeAssistantError
        mock_smapi_cls.return_value.async_setup_skill_complete = AsyncMock(
            side_effect=HomeAssistantError("SMAPI error")
        )

        result = await hass.config_entries.flow.async_configure(flow_id, {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "smapi_error"


async def test_full_config_flow(hass_with_http, aioclient_mock):
    """Full 4-step flow creates a config entry."""
    hass = hass_with_http

    # Mock LWA code exchange
    aioclient_mock.post(
        "https://api.amazon.com/auth/O2/token",
        json=LWA_CODE_EXCHANGE_RESPONSE,
    )

    # Step 1: init flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # Step 2: submit credentials → auth step
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            CONF_REGION: MOCK_REGION,
            CONF_INVOCATION_NAME: MOCK_INVOCATION_NAME,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth_smapi"
    flow_id = result["flow_id"]

    # Simulate callback storing the auth code
    lookup_key = f"{flow_id}_smapi"
    hass.data.setdefault(DOMAIN, {}).setdefault("auth_codes", {})[lookup_key] = "test_auth_code"

    # Step 3: submit auth → SMAPI setup (patched) → finish
    with patch(
        "custom_components.alexa_proactive.config_flow.SMTPClient"
    ) as mock_smapi_cls:
        mock_smapi_cls.return_value.async_setup_skill_complete = AsyncMock(
            return_value=SMAPI_SETUP_RESULT,
        )
        mock_smapi_cls.return_value.async_get_skill_credentials = AsyncMock(
            return_value={
                "client_id": "amzn1.application-oa2-client.skill_integration_test",
                "client_secret": "amzn1.oa2-cs.v1.skill_integration_test_secret",
            },
        )

        result = await hass.config_entries.flow.async_configure(flow_id, {})

    # Should advance through setup to finish
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "finish"

    # Step 4: submit finish → create entry
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alexa Proactive Events"
    assert result["data"][CONF_CLIENT_ID] == MOCK_CLIENT_ID
    assert result["data"][CONF_REGION] == MOCK_REGION
    assert result["data"][CONF_SKILL_ID] == MOCK_SKILL_ID
    assert result["data"][CONF_VENDOR_ID] == MOCK_VENDOR_ID
