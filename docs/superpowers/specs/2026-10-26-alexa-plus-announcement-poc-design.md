# Alexa+ Announcement POC Package Design

Date: 2026-10-26. Status: approved (design v2, script-first).

## Purpose

A reproducible, script-driven package that lets any technical Alexa developer verify whether the `Alexa.ProactiveNotificationSource` announcement channel fires on an Alexa+ (early access) household. First tester: Rick397 in ha_alexa_proactive issue #1. The integration feature itself is designed only after validation.

## What goes where

`docs/experiments/alexa-plus-announcement-poc/`:

- `README.md`: the recipe, in the order that works, with the traps we hit documented (trigger before endpoint save, ARN-only endpoints, `profile:user_id` linking scope, mandatory `semantics.stateMappings`, State Reporter verification).
- `lambda/index.mjs`: washer endpoint discovery (ModeController + `semantics` Done mapping + `ProactiveNotificationSource` + EndpointHealth), AcceptGrant handling with in-Lambda LWA exchange, ReportState response. Parameterized by env: `PERMISSIONS_CLIENT_ID`, `PERMISSIONS_CLIENT_SECRET`.
- `scripts/common.sh`: SMAPI token helper (refresh-token grant) and `smapi()` curl wrapper.
- `scripts/01-create-skill.sh`: SMAPI POST /v1/skills with a manifest that carries everything in one call: smartHome endpoint (Lambda ARN), EU region, `permissions: alexa::async_event:write` (the "Send Alexa Events" toggle in manifest form), publishing info.
- `scripts/02-deploy-lambda.sh`: AWS CLI role + function create/update from `lambda/index.mjs`.
- `scripts/03-add-trigger.sh`: `aws lambda add-permission --principal alexa-connectedhome.amazon.com --event-source-token <skillId>` (verified to produce a statement identical to the console-created trigger).
- `scripts/04-send-transition.py`: token refresh plus Running -> Done ChangeReport to the EU event gateway.

## Automation map

Scriptable: skill creation, manifest (endpoint, regions, events permission), Lambda deploy, Alexa trigger, transitions. Manual and irreducible: the account-linking config page (SMAPI route returns 404 for smart home skills; five fields, values documented), the OAuth consent in the Alexa app, and a human listening. Token capture is automatic (AcceptGrant exchange inside the Lambda, logged to CloudWatch).

## Validation plan

Dogfood the scripts autonomously on the maintainer account: create a second skill with `01-create-skill.sh`, add its trigger with `03-add-trigger.sh`, and confirm via SMAPI GET that the manifest persisted endpoint and permission. The dispatch proof requires one manual app-enable of that skill (user action). Success criterion for the eventual feature decision: an audible announcement on an Alexa+ household after a transition, with the native announcement channel verified live beforehand.
