# Research Report: AMAZON.MessageAlert rendering requirements and device-specific read-back

**Date**: 2026-10-25
**Depth**: exhaustive
**Confidence**: HIGH (field inventory), MEDIUM (pipeline history)

## Executive Summary

No payload structure beyond the documented `AMAZON.MessageAlert.Activated` schema exists: Amazon's SDK builders and every reference implementation use exactly `state.status`, `state.freshness`, `messageGroup.creator.name`, `messageGroup.count`, and the optional `messageGroup.urgency`. Live testing on the author's EU account showed the pipeline healthy end to end: events are accepted, persisted, and read back with the full creator name on classic screenless devices (Echo Flex, Echo Dot), while the Echo Show cannot read these notifications at all (title-only card, no details, voice read-back reports no notifications), and the Alexa app list never shows them. The reported "degradation" was device-specific rendering, not a pipeline change.

## Findings

### 1. Complete field inventory (HIGH)

- Official schema (developer.amazon.com/en-US/docs/alexa/smapi/schemas-for-proactive-events.html): `messageGroup` has `creator.name` (required), `count` (required), `urgency` (optional enum). `state.status` UNREAD/FLAGGED, `state.freshness` NEW/OVERDUE. Nothing else.
- Reference implementations agree: lucarosellini/proactive-events-standalone-sender template and Alexa.NET.ProactiveEvents `MessageReminderGroup.cs` (creator, count, optional urgency, nothing more).
- GitHub code search across org:alexa found no MessageGroup/urgency SDK models beyond these; no display metadata fields exist client-side.
- Empirical: `urgency: URGENT` added to an otherwise identical multicast produced no rendering change (202 accepted, same behavior on all devices).

### 2. Device-specific read-back (HIGH, first-hand experiments)

Same account, same fresh record, "Alexa, do I have notifications":

- Echo Flex: reads full creator name ("hai un messaggio da senza urgenza").
- Echo Dot (older, no screen): reads full creator name ("da test dot").
- Echo Show (kitchen): "non hai nessuna notifica"; delivery shows a card with the sender as title; tapping shows no details.
- Alexa app: never lists development-stage skill notifications, while devices read them; the app list appears to be a separate channel.

### 3. Persistence and history (MEDIUM)

- Home Assistant recorder DB (events/call_service) gives exact send history; on this account real notifications (la lavatrice, scuola di Nora) fired on October 23-25, the last at 07:08 on October 25, hours before any code change that day, and the user recalls sender rendering historically; the exact date the Show stopped rendering could not be determined from logs (user does not remember which devices spoke before).
- Historical sources confirm rich read-back existed: Medium proactive events guide ("Alexa, what are my old notifications?"), StackOverflow 2021 ("Alexa speaks correctly" for creator name).
- Alexa-Notify-Bridge thread (community.home-assistant.io, October 8, 2026): R91 confirms persistent notification works on his account (NA), while under Alexa+ the ring/chime may not trigger, the inverse of other reports; the thread's own solution direction pairs a TTS announcement via Alexa Media Player with the proactive ring because announcement rendering cannot be relied on.
- LinkedIn post by a summer-2025 intern on the Alexa Proactive Notifications team shows the team was building new event-sourcing frameworks in 2025; consistent with a pipeline in flux, though no October 2026 EU A/B evidence was found publicly.

### 4. What was ruled out (HIGH)

- The day's integration changes: one inbound-only routing fix; all other files md5-identical; send path untouched; rich rendering survived the deploy; a live revert experiment (old views.py + restart) produced identical behavior to the fixed code. Notification-permission toggle produced no change. `urgency` no change.

## Confidence Assessment

- Field inventory complete: HIGH (docs + SDK builders + reference implementations + live test).
- Show-specific reader failure: HIGH (three-device controlled comparison, same record).
- App list gap for dev skills: MEDIUM (consistent all day on this account; could vary by account/stage).
- Show firmware as root cause: PLAUSIBLE, unverified (no public firmware notes found).

## Sources

1. https://developer.amazon.com/en-US/docs/alexa/smapi/schemas-for-proactive-events.html : authoritative schema, MessageAlert section.
2. https://github.com/stoiveyp/Alexa.NET.ProactiveEvents : MessageReminder.cs / MessageReminderGroup.cs builders.
3. https://github.com/lucarosellini/proactive-events-standalone-sender : message-template.json reference payload.
4. https://medium.com/swlh/get-started-with-amazon-alexa-skills-proactive-events-api-5b082bcb282c : historical read-back behavior.
5. https://stackoverflow.com/questions/66328865/ : 2021 creator name read-back working.
6. https://community.home-assistant.io/t/alexa-notify-bridge-persistent-yellow-ring-notifications-for-your-echo-devices/1025197 : R91/Ltek October 2026, persistence works on NA account, AMP TTS pairing pattern.
7. https://www.linkedin.com/posts/ka-long-ngai_this-summer-i-helped-alexa-proactively-notify-activity-7359736613263839232-SKGL : Proactive Notifications team activity 2025.
8. First-hand experiments on the author's account, October 25, 2026: recorder DB send history, three-device read-back matrix, revert experiment, urgency A/B.

## Addendum (same day, evening): GitHub-wide search for Show-specific notification formats

- 20-repo census of public code referencing `AMAZON.MessageAlert.Activated` (Voxa, ask-utils, Alexa.NET.ProactiveEvents, lucarosellini, jallwork, xavidop, dabblelab samples): every sender/builder uses the identical documented payload; no Show-specific fields, display metadata, or alternative format exists within the custom-skill proactive events path.
- A separate official format that DOES produce spoken announcements on the Echo Show exists, but on the smart-home add-on path: `Alexa.ProactiveNotificationSource` Interface 3.0 (developer.amazon.com/docs/alexaplus/device-apis/alexa-proactivenotificationsource.html). Example use case in the doc: "when their washing machine cycle completes". The add-on declares notification triggers in discovery (Alexa.Cooking statuses, or ModeController/RangeController stateMappings with `Alexa.States.Done`/`Stuck`/`Full` plus `semantics`), then an `Alexa.ChangeReport` triggers an immediate announcement on Echo Dot, Echo Plus, Echo Show and Echo Spot. Italian (IT) is among the supported languages. This is the announced-notification channel, distinct from the custom-skill notification pipeline.
- Notify Me (certified skill) demonstrably renders and reads back on an Echo Show 5 (danpomahony/puppy-tracker-dev#101): certified-skill notifications render on Show, reinforcing that the Show gap is dev-stage and/or device-specific rather than a missing format.

## Final matrix (evening, after variant sweep)

Payload variants sent and accepted (all 202): FLAGGED status, OVERDUE freshness, urgency URGENT, unicast audience, count 2, localizedattribute: prefix in creator.name (the last rejected with 400 schema validation; unpublished schemas return an undocumented generic 500 instead of a clean rejection; live stage returns 403 "No skill for LWA clientId").

Read-back results: Echo Dot and Echo Flex read every record with the full creator name regardless of variant. Echo Show counts the records correctly ("3 nuove notifiche") but never renders creator details: card title only, no details on tap, voice read-back gives counts without senders. The Alexa app lists none.

Conclusion: the persistent store is healthy and variant-independent; the Echo Show's notification reader is the single broken consumer on this account. No payload variation can address it. Practical workaround for Show locations: pair the proactive ring with a TTS announcement via alexa_media_player, gated by existing quiet-hours logic.
