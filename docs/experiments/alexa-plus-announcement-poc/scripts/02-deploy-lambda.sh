#!/usr/bin/env bash
# Deploy the washer Lambda: execution role (created if missing), function
# create-or-update, env vars, and the Alexa appkit permission so the console
# and test invocations work. The smart home trigger itself is 03-add-trigger.sh.
# Env: LAMBDA_NAME (default washer-poc), AWS_REGION_LAMBDA (default eu-west-1),
#      PERMISSIONS_CLIENT_ID, PERMISSIONS_CLIENT_SECRET
set -euo pipefail
cd "$(dirname "$0")"

LAMBDA_NAME="${LAMBDA_NAME:-washer-poc}"
REGION="${AWS_REGION_LAMBDA:-eu-west-1}"
ROLE_NAME="${LAMBDA_NAME}-role"
: "${PERMISSIONS_CLIENT_ID:?set PERMISSIONS_CLIENT_ID from the skill PERMISSIONS page}"
: "${PERMISSIONS_CLIENT_SECRET:?set PERMISSIONS_CLIENT_SECRET from the skill PERMISSIONS page}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "creating role $ROLE_NAME"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --output text >/dev/null
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10  # IAM propagation
fi

cd ../lambda && zip -q function.zip index.mjs && cd -

if aws lambda get-function --function-name "$LAMBDA_NAME" --region "$REGION" >/dev/null 2>&1; then
  echo "updating function $LAMBDA_NAME"
  aws lambda update-function-code --function-name "$LAMBDA_NAME" --region "$REGION" \
    --zip-file fileb://../lambda/function.zip --output text >/dev/null
  aws lambda update-function-configuration --function-name "$LAMBDA_NAME" --region "$REGION" \
    --environment "Variables={PERMISSIONS_CLIENT_ID=${PERMISSIONS_CLIENT_ID},PERMISSIONS_CLIENT_SECRET=${PERMISSIONS_CLIENT_SECRET}}" \
    --output text >/dev/null
else
  echo "creating function $LAMBDA_NAME"
  aws lambda create-function --function-name "$LAMBDA_NAME" --region "$REGION" \
    --runtime nodejs20.x --handler index.handler --timeout 10 \
    --role "$ROLE_ARN" --zip-file fileb://../lambda/function.zip \
    --environment "Variables={PERMISSIONS_CLIENT_ID=${PERMISSIONS_CLIENT_ID},PERMISSIONS_CLIENT_SECRET=${PERMISSIONS_CLIENT_SECRET}}" \
    --output text >/dev/null
fi

aws lambda add-permission --function-name "$LAMBDA_NAME" --region "$REGION" \
  --statement-id alexa-appkit --action lambda:InvokeFunction \
  --principal alexa-appkit.amazon.com --output text >/dev/null 2>&1 || true

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}"
echo "LAMBDA_ARN=$LAMBDA_ARN" | tee -a ../.poc-state
echo "deployed: $LAMBDA_ARN"
