# Demo

> 📹 **Video link**: _record and paste here (Loom recommended — see script below)_

## What the demo shows

A real end-to-end run against a live Slack workspace and a live Mailgun account:

1. A compliance-style request is posted in `#suppression-requests`:
   *"Self-exclusion request: test4@gmail.com"*
2. Within ~1 second the bot replies in-thread:
   *"✅ Suppressed test4@gmail.com across 1 tenant(s). Audit: ecc402bd-… React with ❌ within 5 min to roll back (requester only)."*
3. The Mailgun dashboard (Send → Suppressions → Unsubscribes) shows the address — blocked.
4. The requester reacts ❌ on the confirmation. The bot replies:
   *"↩️ Rolled back test4@gmail.com across 1 tenant(s). Audit: ac4847a3-… (rollback of ecc402bd-…)"*
5. The address is gone from Mailgun; the audit log shows two linked rows.

Real artifacts from these runs: [sample audit report](docs/sample-audit-report.md).

## Recording script (2–3 minutes, Loom)

| # | Beat | ~Time | What to show |
|---|------|-------|--------------|
| 1 | Problem | 15s | "Today this is manual: copy the address, log into each email tool, add it by hand, no record." |
| 2 | Architecture | 20s | README flow diagram; mention Socket Mode (no public endpoint), parallel dispatch, audit-first. |
| 3 | Live trigger | 30s | Post an address in Slack → ✅ reply appears → switch to Mailgun suppressions page, refresh, it's there. |
| 4 | Audit trail | 20s | Run `.venv/bin/python scripts/demo_report.py` — point at per-tenant outcomes, timings, masked emails. |
| 5 | Rollback | 20s | React ❌ on the confirmation → ↩️ reply → refresh Mailgun, address gone. |
| 6 | Guards | 20s | React ❌ again → "already rolled back". Mention requester-only + 5-minute window + never-undo-pre-existing. |
| 7 | Code tour | 15s | Scroll README decisions; show `pytest` summary (96 tests) and the healthcheck run. |

Tips: have Slack and the Mailgun suppressions page side by side for beats 3 and 5;
run `scripts/healthcheck.py` beforehand so everything is warm; use a fresh
`testN@gmail.com` so the pre-check shows `was_already_suppressed: false`.

## Screenshots to capture

- [ ] Slack thread: request → ✅ confirmation → ❌ reaction → ↩️ rollback reply
- [ ] Mailgun Unsubscribes page with the address present
- [ ] `scripts/demo_report.py` output in a terminal
- [ ] One structured JSON log line from the bot

Drop them in `docs/screenshots/` and link from the README Demo section.
