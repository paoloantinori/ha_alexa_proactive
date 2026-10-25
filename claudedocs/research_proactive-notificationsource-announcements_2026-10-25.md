# Research Report: Why Alexa.ProactiveNotificationSource announcements do not fire from a personal smart home skill

**Date**: 2026-10-25
**Depth**: exhaustive
**Confidence**: HIGH (root cause), MEDIUM (ecosystem claims)

## Executive Summary

The announcements are silent because our discovery response never told Alexa what our device states MEAN: the ModeController values must be mapped to Amazon's predefined states (`Alexa.States.Done`, `Alexa.States.Stuck`) via a `semantics.stateMappings` object, and the ProactiveNotificationSource condition must reference the Alexa state, not the custom mode value. Amazon support confirmed to another developer that only `Alexa.States.Done` and `Alexa.States.Stuck` generate announcements at all. The feature works through pre-built templates ("Your washer is done") and was designed for device makers, but is implementable by any skill that declares the semantics correctly.

## Findings

### 1. Root cause of tonight's silent POC (HIGH, first-hand + documented)

Our discovery declared `supportedModes` with custom values (`Wash.Cycle.Off/Running/Done`) and a `notificationConditions` entry with `{"comparator": "StateEquals", "value": "Wash.Cycle.Done"}`. Both the 2021 launch blog post and the discovery-objects documentation show the required mechanism: the ModeController capability must carry a `semantics` object with `stateMappings` (for example `{"@type": "States", "name": "Alexa.States.Done", "value": "Wash.Cycle.Done"}`), and the notification condition must use the Alexa state (`Alexa.States.Done`). Without the mapping, Alexa cannot map our mode to an announcement template, and the ChangeReport (accepted with 202) never renders as speech. Source: developer.amazon.com/blogs/alexa/device-makers/2021/08/smart-home-device-status-announcements and /docs/alexa/device-apis/alexa-discovery-objects.html#semantics-object.

### 2. Independent confirmation of the state restriction (HIGH)

A Stack Overflow developer with the identical setup (smart home skill, ProactiveNotificationSource, ModeController, announcements enabled, ChangeReports accepted via the skill debugger with `SmartHomeChangeReportSuccess`) got no announcements. Amazon support's answer through a ticket: **only `Alexa.States.Done` and `Alexa.States.Stuck` generate announcements**. Other states in the docs (Full, cooking statuses) either do not announce or behave inconsistently. Source: stackoverflow.com/questions/79877017.

### 3. The feature's design audience and history (HIGH)

Launched August 31, 2021 as "Smart Home Device Status Announcements" in the device-makers blog, with GE Appliances, iRobot, Eufy, Anova and Samsung as launch implementers. Announcements are pre-built templates keyed on friendly names and Alexa states; no custom message text is possible. The interface documentation now lives under the alexaplus device APIs, which originally suggested Alexa+ gating; that hypothesis is now downgraded because the parsimonious explanation (missing semantics) accounts for all observations, and the Stack Overflow answer implies the feature works for regular skills when configured correctly. Source: the 2021 blog post.

### 4. Ecosystem state for hobbyists (MEDIUM)

- SinricPro (a Works with Alexa certified hobbyist bridge) still lists "Support Proactive Alexa notifications" as an open feature request, implying even certified bridges have not shipped it. Source: github.com/sinricpro/feature-requests/issues/74.
- The hobbyist community routes spoken announcements through certified announcer skills: Voice Monkey (API + Alexa routines, supports Echo Show text and images), Notify Me style skills, and for Home Assistant users the alexa_media_player TTS announce path. Source: forum.universal-devices.com/topic/33771 and community threads.
- No verified report was found of a personal, uncertified skill successfully firing a ProactiveNotificationSource announcement; the Stack Overflow question ("has anybody managed...?") remains the strongest public trace, answered only with the states restriction.

### 5. First-hand POC evidence from tonight (HIGH)

Everything up to the announcement works from a personal account in one evening: hybrid HTTPS smart-home declaration is accepted by SMAPI but never dispatched (Lambda-only at runtime); a console-created smart home skill with a Lambda ARN, account linking (LWA, scope `profile:user_id`), the "Send Alexa Events" permission, and the AcceptGrant flow all function; ChangeReports are accepted (202) and update device state. The only missing piece was the semantics mapping.

## Confidence Assessment

- Missing `semantics.stateMappings` as root cause: HIGH (documented mechanism + identical independent failure + our own 202-accepted-but-silent behavior).
- Only Done/Stuck announce: MEDIUM-HIGH (single Amazon support answer relayed through Stack Overflow).
- Alexa+ gating: LOW as primary cause (downgraded; cannot be fully excluded for the EU classic pipeline until the semantics fix is tested).
- Hobbyist ecosystem forced onto certified announcer skills: MEDIUM (consistent community evidence, no counterexamples found).

## Follow-ups

- Apply the fix: add `semantics.stateMappings` (Wash.Cycle.Done → Alexa.States.Done) to the ModeController capability and change the notification condition to `StateEquals Alexa.States.Done`; redeploy, rediscover, resend the Running → Done transition.
- If announcements still do not fire after the semantics fix, the Alexa+ gating hypothesis returns as primary.

## Sources

1. https://stackoverflow.com/questions/79877017 : identical failure; Amazon support states only Alexa.States.Done and Stuck announce.
2. https://developer.amazon.com/en-US/blogs/alexa/device-makers/2021/08/smart-home-device-status-announcements : launch post; semantics.stateMappings mechanism; states Done/Stuck/Full; device-maker audience.
3. https://developer.amazon.com/en-US/docs/alexa/device-apis/alexa-discovery-objects.html : semantics object and stateMappings format.
4. https://developer.amazon.com/docs/alexaplus/device-apis/alexa-proactivenotificationsource.html : current interface documentation.
5. https://github.com/sinricpro/feature-requests/issues/74 : certified bridge still lacks the feature.
6. https://forum.universal-devices.com/topic/33771 : hobbyist announcements via Voice Monkey; links the 2021 announcement.
7. First-hand experiments, October 25, 2026: full personal-account smart home chain built and accepted, announcements silent without semantics.

## Addendum (same night, ~21:00): semantics fix applied and tested

The fix was applied and verified end to end: discovery redeployed with `semantics.stateMappings` (Wash.Cycle.Done → Alexa.States.Done) and the notification condition changed to `StateEquals Alexa.States.Done`; Alexa received the fresh discovery (directive in CloudWatch at 20:38:47); a fresh Running → Done transition was accepted (202 + 202). No announcement fired.

Do Not Disturb was excluded as a cause: all speaker devices (Cucina/Show, Bagno, Lavanderia, Sound System, Fire TV) report DND off via the alexa_media_player `switch.*_do_not_disturb` entities read from Home Assistant; only light bulbs have DND on, which does not affect announcements.

Conclusion update: with semantics correct per documentation, DND excluded, opt-in enabled, tokens valid, and events accepted, the primary hypothesis returns to Amazon-side gating of announcement delivery for non-partner, non-Alexa+ households (the interface lives in the alexaplus device APIs, and the Stack Overflow reporter hit the identical wall). The complete chain remains reproducible and accepted up to the final render; the gate is on Amazon's side. The practical spoken-announcement path for a personal setup remains a certified announcer channel (alexa_media_player TTS, Voice Monkey).

## Second addendum (same night, ~22:00): direct evidence via State Reporter

The Developer Console State Reporter (developer.amazon.com/alexa/console/ask/devices) shows Lavatrice Prova with Alexa.ModeController/Wash.Cycle/mode = Wash.Cycle.Done, timeOfSample 2026-10-25T20:54:30 UTC, matching to the second the ChangeReport sent at 21:54 local. This is direct Amazon-side evidence that: the semantics-corrected discovery was ingested (the Wash.Cycle instance exists only in our discovery), and the ChangeReport was processed into device state. The full chain skill → event gateway → state update is therefore log-verified end to end. The Device Log of an Echo device capturing events during the same seconds shows no announcement-related activity. What remains unverified: whether the native announcement channel was alive at test time (no-noise constraint) and whether Amazon honors the semantics/notification wiring specifically for the announcement pipeline. Hypothesis ranking is unchanged: Amazon-side gating of announcement rendering (Alexa+ or partner certification) is primary; the State Reporter page is the cheapest future retest surface, together with a morning native-announce sanity check.
