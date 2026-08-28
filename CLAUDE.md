# Alexa Proactive Events — Project Guide

## Architecture

This is a Home Assistant custom integration that sends proactive notifications to Alexa devices via Amazon's Proactive Events API.

### File Map

| File | Purpose |
|------|---------|
| `__init__.py` | Service wiring: registers `alexa_proactive.send`, manages config entry lifecycle; reads `alexa_user_id` from `entry.data` |
| `api.py` | LWA OAuth2 client: auth code flow for SMAPI, `client_credentials` grant for Proactive Events (using skill-specific credentials); per-scope token caching (60s expiry buffer); `invalidate_token()` for forced refresh |
| `config_flow.py` | 4-step config flow: credentials → LWA authorization → SMAPI skill setup → finish; validates and normalizes the invocation name (helpers in `models.py`) |
| `const.py` | All constants: URLs, scopes, locale maps (17 locales), country/language detection tables |
| `models.py` | Alexa interaction models for 17 locales with `_build_model()` factory and native utterance samples; invocation-name `normalize_invocation_name()` / `validate_invocation_name()` |
| `proactive.py` | Proactive Events API client: payload builder, region-aware URLs, retries on 403 with cache invalidation; INFO-level send trail (accepted status, referenceId) |
| `smapi.py` | SMAPI client: skill CRUD, manifest management, concurrent model upload via `asyncio.gather`, SSL type detection via executor; `async_upload_models()` powers the options-flow rename |
| `views.py` | `HomeAssistantView` subclass acting as the Alexa skill HTTPS endpoint; persists the captured user ID into `entry.data` |
| `services.yaml` | Service definition for HA UI |
| `strings.json` | Config flow step titles, descriptions, error messages |
| `translations/en.json` | English translations for config flow UI strings |
| `tests/` | Unit suite: `importlib.util` module loading with `homeassistant` fully mocked in `conftest.py` |
| `tests_integration/` | Integration suite: real HA fixtures via pytest-homeassistant-custom-component (`hass`, `aioclient_mock`, `MockConfigEntry`) |
| `pyproject.toml` + `requirements_test.txt` | pytest config (`asyncio_mode = auto`) and test dependencies |
| `hacs.json` | HACS metadata (custom repository) |

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
- **Unicast vs Multicast**: If `alexa_user_id` is captured from the skill endpoint, notifications target that user (Unicast); it is persisted into `entry.data`, so the targeting survives HA restarts. Otherwise, all subscribers get them (Multicast).
- **Invocation-name validation**: Setup and the options-flow rename normalize user input (lowercase, collapsed whitespace, typographic apostrophes mapped to ASCII) and reject names Amazon would refuse (must start with a letter; Unicode letters, digits, combining marks, space, `'` `.` `-`). The check is a locale-agnostic subset: Amazon applies stricter per-locale rules (en-US requires numbers spelled out and disallows hyphens).
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
- **Invocation names are per-locale**: Amazon builds interaction models only for lowercase names, but the full rule set differs per locale (en-US: numbers spelled out, no hyphens; ja-JP allows kana-only single words). The shipped defaults include Arabic, Hindi, and Japanese, so validation must be Unicode-aware, not ASCII.
- **hass-cli `--arguments` is string-typed**: it parses to `Dict[str, str]`, and HA's strict service validation rejects strings where the schema wants an int (400 with empty body). Pass string fields only and rely on defaults. hass-cli lives on the dev host, not on the `ha` SSH target.

### Testing

Two suites with different harnesses. Run them as separate pytest invocations: a single combined run mixes the mocked and real-HA conftest strategies and breaks.

```bash
pip install --user -r requirements_test.txt   # pytest, pytest-asyncio, pytest-homeassistant-custom-component
python -m pytest tests/ -v                    # unit suite: homeassistant fully mocked in conftest
python -m pytest tests_integration/ -q        # integration suite: real HA fixtures via the plugin
```

Integration-suite notes: the plugin's `pytest11` entry point is named `homeassistant` and auto-imports the pinned real Home Assistant; blocking it with `-p no:homeassistant` breaks fixtures. `aioclient_mock` only intercepts sessions created through HA's `async_get_clientsession`, while this integration creates raw `aiohttp.ClientSession`; the autouse `mock_component_sessions` fixture in `tests_integration/conftest.py` patches `LWAClient._get_session` and seeds `ProactiveClient._session` onto the mocked session, so keep those code paths in mind when adding outbound-HTTP tests.

### Release & Deployment

Users install via HACS and consume GitHub releases; the home instance tracks master via manual scp.

Release: bump `version` in `custom_components/alexa_proactive/manifest.json`, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. The `Release` workflow (`.github/workflows/release.yml`) zips `custom_components/alexa_proactive` and attaches `alexa_proactive.zip` to the release; it needs the `permissions: contents: write` block (added 2026-08-28 after the first-ever run failed with "Resource not accessible by integration"). Then add the notes with `gh release edit vX.Y.Z --notes-file <file>` and verify the run went green and the asset is attached before announcing the release.

Home instance deploy: back up `ha:/homeassistant/custom_components/alexa_proactive/` first, scp the changed files (translations go under `translations/`), verify checksums on the target, restart HA (ask first), then confirm the reload via fresh `__pycache__` timestamps and the config entry state in `.storage/core.config_entries`.

### Development Server

**Before starting or restarting the HA dev server, read `docs/dev-server.md` in full.**
It contains the exact proven steps, including the non-obvious external_url setup via WebSocket.
Common mistakes (editing storage files directly, missing trusted_proxies) are documented there.
