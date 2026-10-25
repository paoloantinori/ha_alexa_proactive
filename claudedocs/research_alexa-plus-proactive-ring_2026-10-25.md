# Research Report: Alexa+ impact on skill proactive notification rings, for issue #1 reply

**Date**: 2026-10-25
**Depth**: exhaustive
**Confidence**: HIGH (core findings), with per-finding levels below

## Executive Summary

Rick397's comment on paoloantinori/ha_alexa_proactive#1 is correct on every point I could verify against primary sources, and the Alexa+ ring suppression they identified is independently corroborated by a second reporter on a different project (Alexa-Notify-Bridge). The `views.py` routing bug is confirmed by Amazon's own documentation. Alexa+ early access has been pushed to Prime accounts without request since January 2026 and reached Italy in April 2026, so both the original reporter (US, August) and Rick397 (Italy, October) fit the timeline.

## Findings

### 1. Event type mismatch in views.py (CONFIRMED, HIGH)

Amazon's SMAPI documentation (en-US, current) documents the proactive subscription change request sent to skill endpoints as:

```json
"request": {
  "type": "AlexaSkillEvent.ProactiveSubscriptionChanged",
  "requestId": "string",
  "timestamp": "string",
  "body": {
    "subscriptions": [ { "eventName": "string" } ]
  }
}
```

Source: developer.amazon.com/en-US/docs/alexa/smapi/proactive-events-api.html. Corroborated by Amazon's generated SDK models (discriminator `AlexaSkillEvent.ProactiveSubscriptionChanged`, payload class `ProactiveSubscriptionChangedBody` mapped to `body`) and an SDK GitHub issue where a developer observed the same wire type. Our `views.py:75` routes `AlexaSkillEvent.SkillProactiveSubscriptionChanged`, which never matches; the handler's `body.subscriptions` extraction is correct. Rick397's log report matches the documented type exactly.

Note the asymmetry that caused the bug: the manifest subscription eventName is `SKILL_PROACTIVE_SUBSCRIPTION_CHANGED` (uppercase, Skill-prefixed; our `smapi.py:431` is correct and working), while the wire request type has no `Skill` segment.

### 2. Alexa+ suppresses the yellow ring for skill notifications (CORROBORATED, HIGH for the correlation, MEDIUM for universality)

Independent second report found in the Home Assistant Community thread for Alexa-Notify-Bridge (a separate project using the same proactive events mechanism), dated before October 9, 2026: with the account enrolled in the Alexa+ early access preview, the physical alerts (yellow LED ring and chime) do not trigger; the notification still arrives and is readable by voice; leaving the Alexa+ preview immediately restores the yellow ring. Identical mechanism to Rick397's A/B test on our integration.

Divergence between the two reporters: Rick397's first-party package alerts still ring under Alexa+, while the Alexa-Notify-Bridge reporter says package delivery alerts broke on their account too. That suggests the suppression varies across Alexa+ rollout groups rather than being a single stable behavior, and it is Amazon-side, outside any integration's control.

No Amazon documentation or official acknowledgment found. No contradicting reports found.

### 3. Alexa+ rollout timeline (CONFIRMED, HIGH)

- US: Alexa+ launched in early access spring 2025; one million early-access users by mid-2025 (punto-informatico via The Verge).
- January 2026: Amazon began enrolling all Prime members with supported devices in Alexa+ early access without a waitlist request; users can leave by voice ("Alexa, esci da Alexa Plus" in Italy; exit command per Wired Italia). Source: Wired Italia, 30.01.2026.
- Italy: Alexa+ early access launched 15 April 2026, after US and UK (pasqualepillitteri.it; corroborated by Amazon.it product pages and Italian press coverage of Alexa+ Echo bundles).

Consequence for issue #1: meluvalli (North America, reported August 2026) could have been auto-enrolled in Alexa+ without knowing; Rick397 (Italy, October 2026) is inside the Italy early-access window. Asking meluvalli about their Alexa+ status is the open question that would close the loop on the original report.

### 4. Voice invocation of dev skills under Alexa+ (UNCORROBORATED, single source: Rick397)

Rick397 reports that under Alexa+, "Alexa, open <invocation name>" does not reach the skill (Alexa+ answers by itself), so user ID capture by voice fails; the Developer Console simulator (Test tab) does reach the endpoint and stores the user ID. I found no public corroboration for dev-skill invocation being blocked under Alexa+. Certified skills are invoked by voice on Alexa+ (ZDNet, promoted generative-AI skills). Treat as a plausible single-source observation; the simulator workaround is consistent with our code path (the simulator sends a real LaunchRequest, and `_store_user_id` fires on LaunchRequest).

## Confidence Assessment

- Event type documentation: HIGH (Amazon docs, Amazon SDK source, an SDK GitHub issue, and Rick397's live logs all agree).
- Alexa+ ring suppression: HIGH that the correlation exists as reported (two independent reporters, different projects, different countries, both reproducibly reversible by leaving Alexa+); MEDIUM that it is universal (first-party alerts behaved differently between reporters; possible rollout-group variance).
- Italy and US availability timeline: HIGH (multiple independent press sources plus Amazon pages).
- Dev-skill voice invocation broken under Alexa+: LOW (one reporter, no corroboration found).
- Gap: whether certified third-party skills (for example Notify Me) also lose the ring under Alexa+. meluvalli reports Notify Me rings for them, but their Alexa+ status is unknown; if they are on Alexa+ and Notify Me still rings, the split is dev-stage versus certified handling, which is a sharper diagnosis.

## Sources

1. https://developer.amazon.com/en-US/docs/alexa/smapi/proactive-events-api.html : Amazon SMAPI docs; request type and body shape for ProactiveSubscriptionChanged.
2. https://github.com/alexa/alexa-apis-for-java : Amazon SDK model, `ProactiveSubscriptionChangedRequest.java`, discriminator string.
3. https://github.com/alexa/alexa-skills-kit-sdk-for-java/issues/170 : developer observing `AlexaSkillEvent.ProactiveSubscriptionChanged` on the wire.
4. https://community.home-assistant.io/t/alexa-notify-bridge-persistent-yellow-ring-notifications-for-your-echo-devices/1025197 : independent Alexa+ ring-suppression report (before October 9, 2026).
5. https://www.wired.it/article/alexa-plus-amazon-distribuita-senza-permesso-come-tornare-al-vecchio-assistente-vocale/ : Wired Italia, 30.01.2026, Alexa+ pushed to Prime accounts unrequested; how to revert.
6. https://pasqualepillitteri.it/news/932/alexa-plus-italia-guida-assistente-ai-amazon : Alexa+ Italy early access 15 April 2026.
7. https://www.punto-informatico.it/alexa-plus-otre-un-milione-di-utenti-attivi/ : one million Alexa+ early-access users (mid-2025), via The Verge.
8. https://www.zdnet.com/article/alexa-just-got-three-new-generative-ai-skills-heres-how-to-try-them/ : voice invocation of certified skills on Alexa+.
