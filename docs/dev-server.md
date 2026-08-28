# Development Server Setup

Read this file BEFORE starting or restarting the HA dev server. Every step matters.

## Config Location

The test config lives in the project at `tests_integration/ha_test_config/`.
The whole directory is gitignored: it contains `.storage/` (auth tokens,
onboarding state) plus the recorder DB and logs, so it exists only on this
machine. If it is ever lost, recreate it by following this document from the
top; the `.venv/` survives independently. The `configuration.yaml` it carried
held only proxy, logger, and `trusted_proxies` config (`::/0` for the reverse
proxy).

## One-time Setup

### 1. Create venv and install HA (if not already done)

```bash
uv venv .venv --python 3.12
uv pip install homeassistant --python .venv/bin/python
```

### 2. Fix aiodns/pycares incompatibility

HA 2024.12.5 ships aiodns 3.2.0 which is incompatible with pycares 5.0.1.
After installing HA, downgrade pycares:

```bash
.venv/bin/python -m pip install "pycares==4.4.0"
```

Without this, every DNS lookup crashes with `TypeError: Channel.getaddrinfo() takes 3 positional arguments`.

### 3. Verify symlink exists

```bash
ls -la tests_integration/ha_test_config/custom_components/alexa_proactive
# Should point to ../../custom_components/alexa_proactive
```

If missing:
```bash
ln -sfn "$(pwd)/custom_components/alexa_proactive" tests_integration/ha_test_config/custom_components/alexa_proactive
```

### 4. Onboarding (first run only)

Start HA (see below), then:

```bash
curl -s -X POST http://localhost:8123/api/onboarding/users \
  -H "Content-Type: application/json" \
  -d '{"client_id":"https://localhost:8123","name":"Test","username":"test","password":"testpassword123","language":"en"}'
```

Then complete remaining onboarding steps via the UI, or call the login flow (see "Getting a token" below).

## Starting the Server

```bash
find custom_components -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
nohup .venv/bin/hass --config tests_integration/ha_test_config > /tmp/ha_test.log 2>&1 &
```

Wait ~20s for HA to be ready:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8123
# Should return 200 or 302
```

## Setting external_url (MUST be done after first startup)

The external_url CANNOT be set by editing the storage file; HA ignores it.
It MUST be set via WebSocket `config/core/update`. Only needs to be done once
(persists in `.storage/core.config` until wiped).

```bash
# Get token
FLOW_ID=$(curl -s -X POST http://localhost:8123/auth/login_flow \
  -H "Content-Type: application/json" \
  -d '{"client_id":"https://localhost:8123","handler":["homeassistant",null],"redirect_uri":"https://localhost:8123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['flow_id'])")

AUTH_CODE=$(curl -s -X POST "http://localhost:8123/auth/login_flow/$FLOW_ID" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"https://localhost:8123","username":"test","password":"testpassword123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])")

TOKEN=$(curl -s -X POST http://localhost:8123/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=$AUTH_CODE&client_id=https://localhost:8123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Set URL via WebSocket
python3 -c "
import asyncio, aiohttp
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect('http://localhost:8123/api/websocket') as ws:
            await ws.receive_json()
            await ws.send_json({'type': 'auth', 'access_token': '$TOKEN'})
            await ws.receive_json()
            await ws.send_json({'id':1,'type':'config/core/update','external_url':'https://test.casanande.mywire.org','internal_url':'http://localhost:8123'})
            print('Success:', (await ws.receive_json()).get('success'))
asyncio.run(main())
"
```

## Getting a Token (for any API use)

```bash
FLOW_ID=$(curl -s -X POST http://localhost:8123/auth/login_flow \
  -H "Content-Type: application/json" \
  -d '{"client_id":"https://localhost:8123","handler":["homeassistant",null],"redirect_uri":"https://localhost:8123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['flow_id'])")

AUTH_CODE=$(curl -s -X POST "http://localhost:8123/auth/login_flow/$FLOW_ID" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"https://localhost:8123","username":"test","password":"testpassword123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])")

TOKEN=$(curl -s -X POST http://localhost:8123/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=$AUTH_CODE&client_id=https://localhost:8123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

## Restarting (after code changes)

```bash
pkill -f "hass --config tests_integration/ha_test_config"
sleep 3
find custom_components -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
nohup .venv/bin/hass --config tests_integration/ha_test_config > /tmp/ha_test.log 2>&1 &
```

## Resetting (nuclear option; wipes all stored state)

```bash
pkill -f "hass --config tests_integration/ha_test_config" 2>/dev/null
sleep 2
rm -rf tests_integration/ha_test_config/.storage \
       tests_integration/ha_test_config/*.db* \
       tests_integration/ha_test_config/*.log*
# Then restart; onboarding + external_url will need to be redone
```

## Infrastructure

- The integration is symlinked, so code changes are reflected on restart (clear `__pycache__`)
- Logs go to `/tmp/ha_test.log` (volatile) and `tests_integration/ha_test_config/home-assistant.log`
- External reverse proxy (OpenResty on the router) terminates TLS and forwards to HA on port 8123
- Credentials: user `test`, password `testpassword123`

## Common Mistakes

- **pycares 5.0.1 breaks aiodns 3.2.0**: downgrade to pycares 4.4.0 after `uv pip install homeassistant`
- **Editing core.config storage file directly does NOT work**: use WebSocket `config/core/update`
- **Missing `::/0` in trusted_proxies**: needed to accept requests from any IPv6 source through the reverse proxy
- **Forgetting to clear `__pycache__`**: old bytecode masks code changes on restart
