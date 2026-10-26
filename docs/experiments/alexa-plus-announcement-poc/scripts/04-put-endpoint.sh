#!/usr/bin/env bash
# Attach the Lambda endpoint to the skill. Must run AFTER 03-add-trigger.sh:
# manifest validation checks that the Lambda already carries the smart home
# trigger for this skill, and fails creation/update otherwise.
# Env: LAMBDA_ARN, SKILL_ID (or .poc-state)
set -euo pipefail
cd "$(dirname "$0")"
. ./common.sh

: "${LAMBDA_ARN:?set LAMBDA_ARN}"
if [ -z "${SKILL_ID:-}" ]; then
  SKILL_ID=$(grep '^SKILL_ID=' ../.poc-state | cut -d= -f2-)
fi
: "${SKILL_ID:?SKILL_ID missing}"

CURRENT=$(smapi GET "/v1/skills/$SKILL_ID/stages/development/manifest")
BODY=$(echo "$CURRENT" | head -n -1); CODE=$(echo "$CURRENT" | tail -n1)
[ "$CODE" = "200" ] || { echo "manifest GET failed: HTTP $CODE"; echo "$BODY"; exit 1; }

UPDATED=$(echo "$BODY" | python3 -c "
import json, sys
wrapped = json.load(sys.stdin)
m = wrapped['manifest']
m['apis']['smartHome']['endpoint'] = {'uri': '$LAMBDA_ARN'}
m['apis']['smartHome']['regions'] = {'EU': {'endpoint': {'uri': '$LAMBDA_ARN'}}}
print(json.dumps(wrapped))
")

RESP=$(smapi PUT "/v1/skills/$SKILL_ID/stages/development/manifest" "$UPDATED")
echo "HTTP $(echo "$RESP" | tail -n1)"
echo "endpoint update submitted; check status:"
sleep 15
smapi GET "/v1/skills/$SKILL_ID/status?resource=manifest" | head -n -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['manifest']['lastUpdateRequest']['status'])"
