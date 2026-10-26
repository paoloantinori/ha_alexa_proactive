#!/usr/bin/env bash
# Shared helpers. Source this file from the numbered scripts.
# Required environment:
#   SMAPI_REFRESH_TOKEN  LWA refresh token with alexa::ask:skills:readwrite
#   SMAPI_CLIENT_ID      LWA client id of the same security profile
#   SMAPI_CLIENT_SECRET  LWA client secret of the same security profile
#   VENDOR_ID            your Amazon developer vendor id (developer console)
# Optional:
#   SMAPI_ACCESS_TOKEN   skip the refresh if you already have a token
set -euo pipefail

SMAPI_BASE="${SMAPI_BASE:-https://api.amazonalexa.com}"

smapi_token() {
  if [ -n "${SMAPI_ACCESS_TOKEN:-}" ]; then
    echo "$SMAPI_ACCESS_TOKEN"
    return
  fi
  : "${SMAPI_REFRESH_TOKEN:?set SMAPI_REFRESH_TOKEN or SMAPI_ACCESS_TOKEN}"
  : "${SMAPI_CLIENT_ID:?set SMAPI_CLIENT_ID}"
  : "${SMAPI_CLIENT_SECRET:?set SMAPI_CLIENT_SECRET}"
  curl -s -X POST https://api.amazon.com/auth/O2/token \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode grant_type=refresh_token \
    --data-urlencode refresh_token="$SMAPI_REFRESH_TOKEN" \
    --data-urlencode client_id="$SMAPI_CLIENT_ID" \
    --data-urlencode client_secret="$SMAPI_CLIENT_SECRET" \
    --data-urlencode 'scope=alexa::ask:skills:readwrite alexa::ask:models:readwrite' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

smapi() {
  local method="$1" path="$2" body="${3:-}"
  local token; token="$(smapi_token)"
  if [ -n "$body" ]; then
    curl -s -X "$method" "$SMAPI_BASE$path" \
      -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
      -d "$body" -w '\n%{http_code}'
  else
    curl -s -X "$method" "$SMAPI_BASE$path" \
      -H "Authorization: Bearer $token" -w '\n%{http_code}'
  fi
}
