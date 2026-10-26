#!/usr/bin/env bash
# Add the Alexa Smart Home trigger to the Lambda. This is the statement the
# Alexa console checks before it accepts the endpoint: principal
# alexa-connectedhome.amazon.com gated on the skill id via --event-source-token.
# The CLI statement is identical to the one the AWS console creates.
# Env: LAMBDA_NAME (default washer-poc), AWS_REGION_LAMBDA (default eu-west-1), SKILL_ID
set -euo pipefail

LAMBDA_NAME="${LAMBDA_NAME:-washer-poc}"
REGION="${AWS_REGION_LAMBDA:-eu-west-1}"
if [ -z "${SKILL_ID:-}" ] && [ -f "$(dirname "$0")/../.poc-state" ]; then
  SKILL_ID=$(grep '^SKILL_ID=' "$(dirname "$0")/../.poc-state" | cut -d= -f2-)
fi
: "${SKILL_ID:?set SKILL_ID or run 01-create-skill.sh first}"

aws lambda add-permission --function-name "$LAMBDA_NAME" --region "$REGION" \
  --statement-id "alexa-sh-${SKILL_ID: -12}" \
  --action lambda:InvokeFunction \
  --principal alexa-connectedhome.amazon.com \
  --event-source-token "$SKILL_ID" --output text >/dev/null

echo "trigger added for $SKILL_ID on $LAMBDA_NAME"
