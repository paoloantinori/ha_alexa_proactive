"""Constants for the Alexa Proactive Events integration."""

DOMAIN = "alexa_proactive"

# Login with Amazon (LWA) OAuth2
LWA_TOKEN_URL = "https://api.amazon.com/auth/O2/token"

# Proactive Events API endpoints by region
PROACTIVE_API_URLS = {
    "na": "api.amazonalexa.com",
    "eu": "api.eu.amazonalexa.com",
    "fe": "api.fe.amazonalexa.com",
}

# SMAPI base URL
SMAPI_BASE_URL = "https://api.amazonalexa.com"

# Config entry keys
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_REGION = "region"
CONF_WEBHOOK_ID = "webhook_id"

# LWA OAuth2 scopes
SCOPE_PROACTIVE = "alexa::proactive_events"
SCOPE_SMAPI = "alexa::ask:skills:readwrite"

# Service names and fields
SERVICE_SEND = "send"
CONF_SENDER = "sender"
CONF_COUNT = "count"

# Default values
DEFAULT_SENDER = "Home Assistant"
DEFAULT_COUNT = 1
DEFAULT_REGION = "eu"

# Alexa event schema
EVENT_SCHEMA = "AMAZON.MessageAlert.Activated"