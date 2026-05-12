"""Constants for the Alexa Proactive Events integration."""

DOMAIN = "alexa_proactive"

# Login with Amazon (LWA) OAuth2
LWA_TOKEN_URL = "https://api.amazon.com/auth/O2/token"
LWA_AUTH_URL = "https://www.amazon.com/ap/oa"

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
CONF_INVOCATION_NAME = "invocation_name"
CONF_SKILL_ID = "skill_id"
CONF_VENDOR_ID = "vendor_id"
CONF_WEBHOOK_URL = "webhook_url"
CONF_ALEXA_USER_ID = "alexa_user_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_LOCALES = "locales"

# LWA OAuth2 scopes
SCOPE_PROACTIVE = "alexa::proactive_events"
SCOPE_SMAPI = "alexa::ask:skills:readwrite alexa::ask:models:readwrite"

# Service names and fields
SERVICE_SEND = "send"
CONF_SENDER = "sender"
CONF_COUNT = "count"

# Default values
DEFAULT_SENDER = "Home Assistant"
DEFAULT_COUNT = 1
DEFAULT_REGION = "eu"
DEFAULT_INVOCATION_NAME = "ping me"
DEFAULT_LOCALE = "en-US"

LOCALE_LABELS: dict[str, str] = {
    "ar-SA": "Arabic (Saudi Arabia)",
    "de-DE": "German (Germany)",
    "en-AU": "English (Australia)",
    "en-CA": "English (Canada)",
    "en-GB": "English (United Kingdom)",
    "en-IN": "English (India)",
    "en-US": "English (United States)",
    "es-ES": "Spanish (Spain)",
    "es-MX": "Spanish (Mexico)",
    "es-US": "Spanish (United States)",
    "fr-CA": "French (Canada)",
    "fr-FR": "French (France)",
    "hi-IN": "Hindi (India)",
    "it-IT": "Italian (Italy)",
    "ja-JP": "Japanese (Japan)",
    "nl-NL": "Dutch (Netherlands)",
    "pt-BR": "Portuguese (Brazil)",
}

COUNTRY_LOCALE_MAP: dict[str, str] = {
    "SA": "ar-SA",
    "AT": "de-DE",
    "AU": "en-AU",
    "BE": "nl-NL",
    "BR": "pt-BR",
    "CA": "en-CA",
    "CH": "de-DE",
    "DE": "de-DE",
    "DK": "en-US",
    "ES": "es-ES",
    "FR": "fr-FR",
    "GB": "en-GB",
    "IN": "hi-IN",
    "IT": "it-IT",
    "JP": "ja-JP",
    "MX": "es-MX",
    "NL": "nl-NL",
    "NO": "en-US",
    "NZ": "en-AU",
    "SE": "en-US",
    "SG": "en-US",
    "US": "en-US",
    "ZA": "en-GB",
}

LANGUAGE_LOCALE_MAP: dict[str, str] = {
    "ar": "ar-SA",
    "de": "de-DE",
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "hi": "hi-IN",
    "it": "it-IT",
    "ja": "ja-JP",
    "nl": "nl-NL",
    "pt": "pt-BR",
}

# Alexa event schema
EVENT_SCHEMA = "AMAZON.MessageAlert.Activated"