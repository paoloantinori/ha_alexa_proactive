# Alexa Proactive Events

A Home Assistant custom integration that sends proactive notifications (yellow ring indicator) to Alexa devices via the Amazon Proactive Events API.

## How It Works

1. **Config Flow**: Enter your Amazon Developer LWA credentials, authorize via Amazon login, and the integration automatically creates an Alexa skill via SMAPI with interaction models for your selected locales. Skill-specific credentials are fetched automatically for sending notifications at runtime.

2. **Skill Endpoint**: A custom HTTP view acts as the Alexa skill endpoint, handling Launch, Intent, and SessionEnded requests.

3. **Proactive Notifications**: Call the `alexa_proactive.send` service from any automation to push a notification to your Alexa devices. Notifications use a service-level `client_credentials` grant (separate from the user authorization), so no user login is needed at runtime. Alexa shows a yellow ring and announces the notification in the format: **"You have N messages from [skill name]: [message]."**

## Prerequisites

1. **Amazon Developer Account**: Create one at [developer.amazon.com](https://developer.amazon.com)

2. **LWA Security Profile**: Create one at the [Security Profiles console](https://developer.amazon.com/settings/console/securityprofile/overview.html) ([docs](https://developer.amazon.com/docs/login-with-amazon/security-profile.html)). You need two things from this profile:

   - **Client ID** and **Client Secret** — found under the Web Settings tab
   - **Allowed Return URLs** — add your HA external URL followed by `/auth/alexa_proactive/callback` (e.g. `https://my-ha.duckdns.org:8123/auth/alexa_proactive/callback`)

3. **Home Assistant External URL**: Must be configured (`Settings > System > Network`) so Alexa can reach the skill endpoint. This typically requires a Nabu Casa subscription, a reverse proxy, or another tunneling solution.

## Installation

### HACS (recommended)

1. Add this repository as a custom HACS repository
2. Search for "Alexa Proactive Events" in HACS
3. Click Install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/alexa_proactive/` directory to your HA `custom_components/` folder
2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services**
2. Click **Add Integration** and search for "Alexa Proactive Events"
3. **Step 1 — Credentials**: Enter your LWA Client ID, Client Secret, select your Alexa API region (EU, NA, or FE), optionally customize the invocation name and select locales (auto-detected from your HA country/language settings)
4. **Step 2 — Authorize**: Click the authorization link, sign in with your Amazon Developer account, and approve. Return to HA and submit.
5. **Step 3 — Skill Setup**: The integration automatically creates the Alexa skill via SMAPI, uploads interaction models for all selected locales concurrently, fetches skill-specific credentials for runtime notifications, and attempts to enable the skill. Enablement may fail if the model hasn't finished processing yet — in that case, enable it manually (see step 6).
6. **Step 4 — Activate**: After setup completes, open the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask), find your skill, and click **Enable** if it's not already enabled. Then say "Alexa, open [invocation name]" on your device to link your account and capture your user ID for unicast notifications.

## Usage

### Service: `alexa_proactive.send`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sender` | string | `"Home Assistant"` | Message text shown after the skill name in the notification |
| `count` | integer | `1` | Number of unread messages (1–99) |

### Notification Format

When a notification is sent, Alexa shows a yellow ring and announces:

> "You have `[count]` messages from `[skill name]`: `[sender]`"

Where:
- **skill name** — the invocation name set during configuration (editable via Options)
- **sender** — the message text you provide in the service call

### Automation Examples

**Basic notification when a door opens:**

```yaml
automation:
  - alias: "Notify Alexa when front door opens"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: alexa_proactive.send
        data:
          sender: "Front Door"
          count: 1
```

**Washing machine done:**

```yaml
automation:
  - alias: "Washing machine finished"
    trigger:
      - platform: state
        entity_id: sensor.washing_machine
        to: "done"
    action:
      - service: alexa_proactive.send
        data:
          sender: "Laundry"
          count: 1
```

**Multiple notifications as a count:**

```yaml
automation:
  - alias: "Unread messages count"
    trigger:
      - platform: state
        entity_id: sensor.unread_messages
    action:
      - service: alexa_proactive.send
        data:
          sender: "Mailbox"
          count: "{{ states('sensor.unread_messages') | int }}"
```

## Regions

| Code | Endpoint |
|------|----------|
| `eu` | Europe (`api.eu.amazonalexa.com`) |
| `na` | North America (`api.amazonalexa.com`) |
| `fe` | Far East (`api.fe.amazonalexa.com`) |

## Troubleshooting

**"Integration not configured" error when calling the service**
- Ensure the config entry is in "Loaded" state (Settings > Devices & Services)

**"Invalid LWA credentials" / "Authorization failed" during setup**
- Verify your Client ID and Client Secret are correct
- Ensure your **Allowed Return URL** in the LWA console matches `https://<your-ha-url>/auth/alexa_proactive/callback`

**"Authorization pending" does not resolve**
- Make sure your HA external URL is reachable from your browser
- Check that the callback URL is registered in the LWA Security Profile's Web Settings

**"SMAPI skill creation failed"**
- Confirm your Amazon Developer account has vendor access ([Alexa Developer Console](https://developer.amazon.com/alexa/console/ask))
- Check the Home Assistant logs for the specific SMAPI error

**Alexa doesn't show the yellow ring**
- Ensure you've enabled the skill in the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) — the automatic enablement step may fail if the interaction model hasn't finished processing. If you see "Skill is not ready for enablement" in the logs, just enable it manually in the console.
- Say "Alexa, open [invocation name]" to trigger user ID capture
- Verify your HA external URL is reachable from the internet

**"Alexa says there was a problem" / INVALID_RESPONSE when opening the skill**
- Ensure your HA external URL uses HTTPS with a valid SSL certificate
- If using a **wildcard SSL certificate** (e.g. `*.yourdomain.com`), the integration auto-detects this and configures the manifest correctly. If you manually updated the skill manifest, make sure `sslCertificateType` is set to `"Wildcard"` (not `"Trusted"`)
- The integration registers per-region endpoints (NA, EU, FE) in the skill manifest. This is required for Echo devices to reach the skill endpoint — proactive notifications work without them, but skill invocation ("Alexa, open [name]") does not

## Architecture

```
custom_components/alexa_proactive/
├── __init__.py        # Service wiring, config entry lifecycle
├── api.py             # LWA OAuth2 client (auth code + client_credentials)
├── config_flow.py     # 4-step setup flow (credentials → authorize → SMAPI → finish)
├── const.py           # Constants (URLs, scopes, locale maps)
├── manifest.json      # HA integration metadata
├── models.py          # Alexa interaction models (17 locales)
├── proactive.py       # Proactive Events API client (retries with cache invalidation)
├── services.yaml      # Service definition for HA UI
├── smapi.py           # SMAPI client for skill CRUD, concurrent model uploads
├── strings.json       # Config flow UI strings
├── translations/
│   └── en.json        # English translations
└── views.py           # Alexa skill endpoint + OAuth callback
```

## License

MIT
