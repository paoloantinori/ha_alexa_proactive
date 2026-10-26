#!/usr/bin/env bash
# Create the smart home skill WITHOUT the endpoint, carrying the
# alexa::async_event:write permission (the manifest form of the console's
# "Send Alexa Events" toggle). The endpoint cannot be included here: manifest
# validation requires the Lambda trigger, and the trigger needs this skill's
# id. 04-put-endpoint.sh attaches it after 03-add-trigger.sh.
# Env: VENDOR_ID, SKILL_NAME (optional, default), LOCALE (default it-IT)
set -euo pipefail
cd "$(dirname "$0")"
. ./common.sh

: "${VENDOR_ID:?set VENDOR_ID}"
SKILL_NAME="${SKILL_NAME:-Washer Announcement POC}"
LOCALE="${LOCALE:-it-IT}"

MANIFEST=$(python3 - "$SKILL_NAME" "$LOCALE" "$VENDOR_ID" <<'PY'
import json, sys
name, locale, vendor = sys.argv[1:4]
print(json.dumps({
    'vendorId': vendor,
    'manifest': {
        'manifestVersion': '1.0',
        'publishingInformation': {'locales': {locale: {'name': name}}},
        'apis': {
            # Endpoint intentionally omitted: manifest validation requires the
            # Lambda trigger to exist first, and the trigger needs this skill's
            # id. 04-put-endpoint.sh adds endpoint and regions once the
            # trigger is in place (the chicken-and-egg that silently fails
            # skill creation when the endpoint is included here).
            'smartHome': {'protocolVersion': '3'}
        },
        # This permission IS the "Send Alexa Events" console toggle.
        'permissions': [{'name': 'alexa::async_event:write'}],
    },
}))
PY
)

RESP=$(smapi POST /v1/skills "$MANIFEST")
BODY=$(echo "$RESP" | head -n -1); CODE=$(echo "$RESP" | tail -n1)
echo "HTTP $CODE"
if [ "$CODE" != "202" ] && [ "$CODE" != "201" ]; then
  echo "$BODY"; echo "creation failed"; exit 1
fi
SKILL_ID=$(echo "$BODY" | python3 -c 'import json,sys; print(json.load(sys.stdin)["skillId"])')
echo "SKILL_ID=$SKILL_ID" | tee ../.poc-state
echo "skill created: $SKILL_ID"
