# Alexa Proactive Events — Project Guide

## Architecture

This is a Home Assistant custom integration that sends proactive notifications to Alexa devices via Amazon's Proactive Events API.

### File Map

| File | Purpose |
|------|---------|
| `__init__.py` | Service wiring: registers `alexa_proactive.send`, manages config entry lifecycle |
| `api.py` | LWA OAuth2 client with `client_credentials` grant, per-scope token caching (60s expiry buffer) |
| `config_flow.py` | 3-step config flow: credentials → SMAPI skill creation → finish |
| `const.py` | All constants: URLs, scopes, defaults, config keys |
| `models.py` | Alexa interaction models (en-US, it-IT) with intent schemas and sample utterances |
| `proactive.py` | Proactive Events API client: payload builder, region-aware URLs, token retry on 403 |
| `smapi.py` | SMAPI client: skill CRUD, manifest management, model upload |
| `views.py` | `HomeAssistantView` subclass acting as the Alexa skill HTTPS endpoint |
| `services.yaml` | Service definition for HA UI |
| `strings.json` | Config flow step titles, descriptions, error messages |

### API Flow

```
Setup (config_flow.py):
  LWA token (alexa::ask:skills:readwrite) → SMAPI creates skill → upload model → enable skill

Runtime (__init__.py → proactive.py):
  LWA token (alexa::proactive_events) → POST /v1/proactiveEvents → yellow ring on Alexa

Skill endpoint (views.py):
  Alexa POST → HomeAssistantView.post() → intent router → JSON response
  First "open ping me" captures user ID for unicast targeting
```

### Key Design Decisions

- **`client_credentials` OAuth**: No user login flow. The integration uses a single LWA Security Profile with `client_credentials` grant for both SMAPI (setup) and Proactive Events (runtime).
- **Two separate scopes**: `alexa::proactive_events` for sending notifications, `alexa::ask:skills:readwrite` for creating the skill. Token caching is per-scope.
- **Custom HTTP view**: `HomeAssistantView` with `requires_auth = False` so Amazon's cloud can reach it directly.
- **Unicast vs Multicast**: If `alexa_user_id` is captured from the skill endpoint, notifications target that user (Unicast). Otherwise, all subscribers get them (Multicast).
- **Automatic retry on 403**: The ProactiveClient retries once with a fresh token if the API returns 403 (expired token).
- **runtime_data pattern**: `entry.runtime_data` holds the `ProactiveClient` instance, set during `async_setup_entry` and cleared during `async_unload_entry`.

### HA Integration Conventions

- All entry points are `async def` functions (`async_setup`, `async_setup_entry`, `async_unload_entry`)
- Service errors use `ServiceValidationError` (user-visible), not `HomeAssistantError` (log-only)
- Config flow uses voluptuous schemas and `async_show_form` / `async_create_entry`
- HTTP views extend `HomeAssistantView` from `homeassistant.components.http`
- The integration uses `hass.helpers.aiohttp_client.async_create_clientsession` for HTTP requests (respects HA proxy settings)

### Alexa Gotchas

- **Region matters**: EU, NA, and FE have separate API endpoints. Wrong region = connection refused.
- **Proactive events schema**: Only `AMAZON.MessageAlert.Activated` is used. Amazon validates the payload strictly.
- **Skill stages**: The integration uses `stages/development` (for dev/test skills). Production skills need certification.
- **Locale matching**: The interaction model must match the skill's locale. Supported: en-US, it-IT.
- **Notification expiry**: Events expire after 1 hour (`_EXPIRY_HOURS = 1` in `proactive.py`).

### Testing

Tests live in `tests/` and use `importlib.util` to load modules without HA's import machinery. `conftest.py` mocks all `homeassistant.*` modules and provides shared fixtures (`ha_error`, fake `HomeAssistantView`, fake `ConfigFlow`).

```bash
python -m pytest tests/ -v          # Run all 120 tests
python -m pytest tests/test_init.py  # Run specific module
```

### Deployment

See the `.claude/` directory for deployment instructions if using the development server.
