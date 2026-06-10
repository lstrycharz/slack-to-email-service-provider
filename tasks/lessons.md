# Lessons

## 2026-06-10 — Slack rich text: the href can lie; the label is the truth
Editing a message draft around an auto-linked email left raw text
`<mailto:test3@gmail.com|t><mailto:est2@gmail.com|est2@gmail.com>` while the user SAW
"test2@gmail.com". Extracting from raw text suppressed two wrong addresses.
**Rule**: for any Slack-text parsing, flatten `<href|label>` to the label first — parse what
the human saw, never composer-internal state. More generally: test parsers against the
platform's *rich/edited* representations, not just clean typed input.

## 2026-06-09 — Slack: scopes ≠ event subscriptions
First live run received zero events despite valid tokens, correct scopes, and bot membership
in the channel. Cause: Event Subscriptions (bot events `message.channels`, `reaction_added`)
were never added — scopes grant API *permission*; event subscriptions make Slack *push*.
Setup docs omitted the step.
**Rule**: any Slack bot setup checklist must include Event Subscriptions with the exact bot
event names, and the healthcheck/live-test plan must include a "did an event actually arrive"
probe (post → expect handler log line) rather than assuming connection == delivery.

## 2026-06-09 — Third-party account vetting is a project risk, not a checkbox
SendGrid's onboarding compliance review declined a fresh free-tier account with no recourse,
after the spec's "To Verify Before Building" had only checked that the *API scope* existed on
the free tier. The unchecked assumption was account *activation* itself.
**Rule**: for any plan that depends on a third-party account, treat signup/activation as
Phase 0's first step and complete it before writing provider-specific code — or pick the
provider with no vetting gate when options are equivalent. Architecture mitigated the cost
here (thin client + provider field meant the pivot touched one module and config), which is
the second half of the lesson: keep external services behind one thin, swappable module.
