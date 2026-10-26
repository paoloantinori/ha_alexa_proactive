# Alexa+ Announcement POC

A script-driven reproduction of the `Alexa.ProactiveNotificationSource` channel: a fake washer whose "cycle finished" state change SHOULD make Alexa announce on all Echo devices. On a classic Alexa household the full chain works (skill, linking, AcceptGrant tokens, ChangeReports accepted and reflected in the State Reporter) but the announcement never renders; the hypothesis under test is that it renders on Alexa+ (early access) households. Everything below is automated except two inherently manual steps: the account-linking config page (no SMAPI route exists for smart home skills) and the OAuth consent in the Alexa app.

## Prerequisites

- An Amazon developer account (vendor id, and LWA credentials with `alexa::ask:skills:readwrite`; `ask configure` from the ASK CLI is the easiest way to obtain a refresh token, or reuse the credentials of an existing SMAPI setup).
- An AWS account with the CLI configured.
- One LWA security profile you control (for account linking later).

## Steps

1. **Deploy the Lambda** (needs the skill's permissions client, so run after step 4 the first time, or run 02 twice):

   ```bash
   export LAMBDA_NAME=washer-poc AWS_REGION_LAMBDA=eu-west-1
   export PERMISSIONS_CLIENT_ID=... PERMISSIONS_CLIENT_SECRET=...
   scripts/02-deploy-lambda.sh
   ```

2. **Create the skill** (no endpoint yet; the events permission `alexa::async_event:write` IS the console's "Send Alexa Events" toggle, set here via manifest):

   ```bash
   export VENDOR_ID=...
   scripts/01-create-skill.sh     # prints SKILL_ID, saved to .poc-state
   ```

3. **Add the smart home trigger** (this is what manifest validation checks before accepting an endpoint; the CLI statement is identical to the console-created one):

   ```bash
   scripts/03-add-trigger.sh      # uses SKILL_ID from .poc-state
   ```

4. **Attach the endpoint** (only now can validation pass; the script re-PUTs the manifest with the ARN and EU region and reports the build status):

   ```bash
   export LAMBDA_ARN=arn:aws:lambda:eu-west-1:<acct>:function:washer-poc
   scripts/04-put-endpoint.sh
   ```

4. **Console, once** (the only manual config): open the skill, PERMISSIONS page, verify "Send Alexa Events" is on (it should already be, from the manifest permission; the page also shows PERMISSIONS_CLIENT_ID/SECRET: set them as Lambda env vars and rerun `02-deploy-lambda.sh`). Then ACCOUNT LINKING: Auth Code Grant, authorization URL `https://www.amazon.com/ap/oa`, token URL `https://api.amazon.com/auth/o2/token`, your LWA profile client id/secret, scope `profile:user_id` (NOT `alexa::voice_service:report_state`: LWA rejects it at consent), redirect URL any HTTPS URL of yours. In the LWA console add the skill's "Alexa Redirect URLs" (three, with your vendor id) to the profile's Allowed Return URLs.

5. **Enable and link** the skill in the Alexa app. The Lambda receives `Alexa.Authorization/AcceptGrant`, exchanges the code, and logs the tokens to CloudWatch (`LWA_EXCHANGE`).

6. **Discover**: "Alexa, discover devices". A "Lavatrice Prova" washer appears. Verify ingestion any time on the console State Reporter page.

7. **Sanity-check the announcement channel**, then send the transition and listen:

   ```bash
   # say: "Alexa, announce: test" (must speak)
   export REFRESH_TOKEN=$(aws logs filter-log-events --region eu-west-1 \
       --log-group-name /aws/lambda/washer-poc --filter-pattern 'LWA_EXCHANGE 200' \
       | grep -o '"refresh_token":"[^"]*"' | tail -1 | cut -d'"' -f4)
   scripts/05-send-transition.py
   ```

## Traps we hit, so you don't have to

- Smart home endpoints accept Lambda ARNs only (HTTPS URLs are rejected by validation, and hybrid custom+smartHome manifests with HTTPS never dispatch).
- Chicken-and-egg: creating the skill WITH the endpoint fails validation asynchronously (the trigger cannot exist before the skill id), and the skill then disappears from the vendor list. Create without the endpoint, add the trigger, then PUT the endpoint (steps 2, 3, 4).
- The console refuses to save the endpoint until the Lambda has the `alexa-connectedhome.amazon.com` trigger with `--event-source-token`: the same check the API manifest validation runs.
- The linking scope must be `profile:user_id`; `alexa::voice_service:report_state` yields "unknown scope" at consent for any client we tried.
- Announcements only trigger for `Alexa.States.Done` and `Alexa.States.Stuck`: the ModeController needs `semantics.stateMappings` mapping your mode value to `Alexa.States.Done`, and the notification condition must reference the Alexa state, not your custom value.
- Alexa announces state CHANGES: send Running first, then Done.
- Announcements are transient voice only; nothing lands in the notification center or the app.

## Result recording

On classic Alexa (EU, October 2026): chain verified end to end, announcement silent, native announcement channel verified working minutes before the test. The open question for Alexa+ households is exactly what this POC measures.
