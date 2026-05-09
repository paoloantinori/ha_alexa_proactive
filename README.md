# Alexa Proactive Events

A Home Assistant custom integration that sends proactive notifications (yellow ring indicator) to Alexa devices via the Amazon Proactive Events API.

## How It Works

1. **Config Flow**: Enter your Amazon Developer LWA credentials. The integration automatically creates an Alexa skill via SMAPI with the correct interaction model and proactive events subscription.

2. **Skill Endpoint**: A custom HTTP view acts as the Alexa skill endpoint, handling Launch, Intent, and SessionEnded requests.

3. **Proactive Notifications**: Call the `alexa_proactive.send` service from any automation to push a notification to your Alexa devices. Alexa shows a yellow ring and announces "You have N messages from [sender]."

## Prerequisites

- **Amazon Developer Account**: Create one at [developer.amazon.com](https://developer.amazon.com)
- **LWA Security Profile**: Create a Security Profile in the Amazon Developer Console with:
  - **Client ID** and **Client Secret** from the Web Settings tab
  - The profile must be granted two OAuth scopes:
    - `alexa::proactive_events` — for sending notifications at runtime
    - `alexa::ask:skills:readwrite` — for automatic skill creation during setup
- **Home Assistant External URL**: Must be configured (`Settings > System > Network`) so Alexa can reach the skill endpoint. This typically requires a Nabu Casa subscription, a reverse proxy, or another tunneling solution.

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
3. **Step 1 — Credentials**: Enter your LWA Client ID, Client Secret, and select your Alexa API region (EU, NA, or FE)
4. **Step 2 — Skill Setup**: The integration validates your credentials and automatically creates the Alexa skill via SMAPI
5. **Step 3 — Activate**: On your Alexa app, enable the skill. Say "Alexa, open ping me" to link your account.

## Usage

### Service: `alexa_proactive.send`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sender` | string | `"Home Assistant"` | Name shown in the notification |
| `count` | integer | `1` | Number of unread messages (1–99) |

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

**"Invalid LWA credentials" during setup**
- Verify your Client ID and Client Secret are correct
- Check that your LWA Security Profile has both required OAuth scopes

**"SMAPI skill creation failed"**
- Confirm your LWA profile has the `alexa::ask:skills:readwrite` scope
- Check the Home Assistant logs for the specific SMAPI error

**Alexa doesn't show the yellow ring**
- Ensure you've enabled the skill in the Alexa app
- Say "Alexa, open ping me" to trigger user ID capture
- Verify your HA external URL is reachable from the internet

**"Scope missing" error**
- Your LWA Security Profile was not granted the required OAuth scope
- Re-create the profile with both `alexa::proactive_events` and `alexa::ask:skills:readwrite`

## Architecture

```
custom_components/alexa_proactive/
├── __init__.py        # Service wiring, config entry lifecycle
├── api.py             # LWA OAuth2 client with token caching
├── config_flow.py     # 3-step setup flow (credentials → SMAPI → finish)
├── const.py           # Constants (URLs, scopes, defaults)
├── manifest.json      # HA integration metadata
├── models.py          # Alexa interaction models (en-US, it-IT)
├── proactive.py       # Proactive Events API client
├── services.yaml      # Service definition for HA UI
├── smapi.py           # SMAPI client for skill CRUD
├── strings.json       # Config flow UI strings
└── views.py           # Alexa skill HTTP endpoint
```

## License

MIT
