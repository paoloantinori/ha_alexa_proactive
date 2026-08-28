# Alexa Proactive Events — Project Guide

## Architecture

This is a Home Assistant custom integration that sends proactive notifications to Alexa devices via Amazon's Proactive Events API.

### File Map

| File | Purpose |
|------|---------|
| `__init__.py` | Service wiring: registers `alexa_proactive.send`, manages config entry lifecycle |
| `api.py` | LWA OAuth2 client: auth code flow for SMAPI, `client_credentials` grant for Proactive Events (using skill-specific credentials); per-scope token caching (60s expiry buffer); `invalidate_token()` for forced refresh |
| `config_flow.py` | 4-step config flow: credentials → LWA authorization → SMAPI skill setup → finish |
| `const.py` | All constants: URLs, scopes, locale maps (17 locales), country/language detection tables |
| `models.py` | Alexa interaction models for 17 locales with `_build_model()` factory and native utterance samples |
| `proactive.py` | Proactive Events API client: payload builder, region-aware URLs, retries on 403 with cache invalidation |
| `smapi.py` | SMAPI client: skill CRUD, manifest management, concurrent model upload via `asyncio.gather`, SSL type detection via executor |
| `views.py` | `HomeAssistantView` subclass acting as the Alexa skill HTTPS endpoint |
| `services.yaml` | Service definition for HA UI |
| `strings.json` | Config flow step titles, descriptions, error messages |
| `translations/en.json` | English translations for config flow UI strings |

### API Flow

```
Setup (config_flow.py):
  User authorizes via LWA auth code (alexa::ask:skills:readwrite alexa::ask:models:readwrite)
  → exchange for tokens → SMAPI creates skill → upload models (concurrent, per-locale) → enable skill

Runtime (__init__.py → proactive.py):
  LWA token via client_credentials (alexa::proactive_events) → POST /v1/proactiveEvents → yellow ring on Alexa

Skill endpoint (views.py — AlexaProactiveView):
  Alexa POST → HomeAssistantView.post() → intent router → JSON response
  First "open ping me" captures user ID for unicast targeting

OAuth callback (views.py — AlexaAuthCallbackView):
  Amazon redirect → /auth/alexa_proactive/callback → stores auth code → config flow exchanges for tokens
```

### Key Design Decisions

- **Hybrid OAuth**: Authorization code flow for SMAPI (needs user identity, persists refresh token), `client_credentials` for proactive events (service-level, no user context). Token caching is per-scope.
- **Multi-locale**: 17 locales with native utterance samples. Config flow auto-detects suggested locales from HA's country/language config. Models uploaded concurrently; manifest only references locales with successful uploads.
- **Custom HTTP view**: `HomeAssistantView` with `requires_auth = False` so Amazon's cloud can reach it directly. Uses `web.Response(body=json_bytes(...))` instead of `self.json()` to bypass gzip compression — Amazon's Alexa dispatcher fails to parse compressed responses.
- **SSL certificate auto-detection**: `_detect_ssl_type()` probes the endpoint's certificate SAN in an executor thread at manifest build time (see Alexa Gotchas for details).
- **Per-region endpoints**: Manifest includes endpoints for all three Alexa regions (NA, EU, FE) in both `apis.custom` and `events` (see Alexa Gotchas for details).
- **Unicast vs Multicast**: If `alexa_user_id` is captured from the skill endpoint, notifications target that user (Unicast). Otherwise, all subscribers get them (Multicast).
- **Automatic retry on 403**: The ProactiveClient invalidates the cached token and retries once with a fresh `client_credentials` grant if the API returns 403.
- **runtime_data pattern**: `entry.runtime_data` holds the `ProactiveClient` instance, set during `async_setup_entry` and cleared during `async_unload_entry`.

### HA Integration Conventions

- All entry points are `async def` functions (`async_setup`, `async_setup_entry`, `async_unload_entry`)
- Service errors use `ServiceValidationError` (user-visible), not `HomeAssistantError` (log-only)
- Config flow uses voluptuous schemas and `async_show_form` / `async_create_entry`
- HTTP views extend `HomeAssistantView` from `homeassistant.components.http`
- The integration currently uses raw `aiohttp.ClientSession` in `LWAClient`, `SMTPClient`, and `ProactiveClient` rather than HA's `async_create_clientsession`. Sessions are created lazily and never explicitly closed — a known deviation from HA best practice.

### Alexa Gotchas

- **Region matters**: EU, NA, and FE have separate API endpoints. Wrong region = connection refused.
- **Proactive events schema**: Only `AMAZON.MessageAlert.Activated` is used. Amazon validates the payload strictly.
- **Skill stages**: The integration uses `stages/development` (for dev/test skills). Production skills need certification.
- **Locale matching**: Supported locales: ar-SA, de-DE, en-AU, en-CA, en-GB, en-IN, en-US, es-ES, es-MX, es-US, fr-CA, fr-FR, hi-IN, it-IT, ja-JP, nl-NL, pt-BR (17 total).
- **Notification expiry**: Events expire after 1 hour (`_EXPIRY_HOURS = 1` in `proactive.py`).
- **Gzip compression breaks Alexa**: HA's `HomeAssistantView.json()` calls `enable_compression()` which gzip-encodes the body when the client sends `Accept-Encoding: gzip`. Amazon's Alexa skill dispatcher can't parse compressed responses and returns INVALID_RESPONSE. The `views.py` endpoint uses `web.Response(body=json_bytes(result))` directly to bypass this.
- **Wildcard SSL certificates**: If the HA endpoint uses a wildcard certificate (e.g. `*.mywire.org`), the manifest must set `sslCertificateType: "Wildcard"` — not `"Trusted"`. Amazon validates the cert type against the actual certificate and rejects mismatches. The `_detect_ssl_type()` method handles this automatically.
- **Per-region endpoints are required**: Alexa's skill invocation pipeline (`apis.custom`) routes through regional endpoints. Without `apis.custom.regions.{NA,EU,FE}.endpoint`, Echo devices get INVALID_RESPONSE even though proactive notifications work (because `events.regions` is a separate path).

### Testing

Tests live in `tests/` and use `importlib.util` to load modules without HA's import machinery. `conftest.py` mocks all `homeassistant.*` modules and provides shared fixtures (`ha_error`, fake `HomeAssistantView`, fake `ConfigFlow`).

```bash
python -m pytest tests/ -v          # Run the full test suite
python -m pytest tests/test_init.py  # Run specific module
```

### Development Server

**Before starting or restarting the HA dev server, read `.claude/dev-server.md` in full.**
It contains the exact proven steps, including the non-obvious external_url setup via WebSocket.
Common mistakes (editing storage files directly, missing trusted_proxies) are documented there.
