# Slack To Email Service Provider

**A Slack bot that instantly puts people on a company's email "do not contact" list — across every email system the company uses — and keeps a permanent record of every action.**

**Status**: Working prototype, demonstrated end-to-end against a real Slack workspace and a real
email provider (Mailgun). Not deployed at any organization — see
[Honest deployment status](#honest-deployment-status).

---

## The problem this solves, in plain words

When someone tells a company **"stop emailing me"**, the company has to actually stop — quickly.
Sometimes it's the law: gambling sites must honor self-exclusion requests, and privacy laws like
GDPR give people the right to be removed.

Here's what that looks like inside many companies today:

1. A request lands in a Slack channel or a ticket: *"Please unsubscribe john@example.com, they self-excluded."*
2. An employee copies the address, logs into email system #1, finds the right page, adds it.
3. Then logs into email system #2 (big companies run several — one per brand or country) and does it again.
4. Hopefully without a typo. Hopefully today, not after the weekend.

That takes **3–10 minutes per request** when it goes well — and until it's done, the person who
asked to be left alone **can still receive marketing emails**. In regulated industries, that gap
isn't just embarrassing, it's a legal exposure. And if a regulator later asks *"prove you handled
this request"*, the answer is buried in someone's memory and a few login histories.

## What this bot does instead

Someone posts the email address in a designated Slack channel. About **one second** later:

- ✅ The address is blocked in **every** configured email system, all at the same time.
- 🧾 A permanent, tamper-evident record is written: who asked, when, what happened in each system.
- 💬 The bot replies in the thread confirming it's done, with a reference number for the record.
- ↩️ Made a mistake? The person who asked can react with ❌ within 5 minutes to undo it —
  and the bot will only undo what *it* did, never a block that already existed for other reasons.

The minutes-long, error-prone, unprovable manual chore becomes a one-second, recorded, reversible
one. That's the whole idea.

A real report generated from the audit log of live test runs (only masked data — the system
never stores plaintext email addresses): **[sample audit report →](docs/sample-audit-report.md)**

---

## How it works (the technical part)

```
Someone posts an email in #suppression-requests
        │
        ▼
Slack Socket Mode WebSocket ──► bot receives the message
        │   (ignores edits, thread replies, other channels, its own messages)
        ▼
Email parser  (parses what the human SAW — Slack link labels, not stale hrefs)
        │
        ▼
For each email:  write a PENDING audit row  ──►  then, per tenant IN PARALLEL:
        │            GET  was it already suppressed?   (rollback safety)
        │            POST add to suppression list      (retry once on 5xx/timeout)
        ▼
Finalize audit row with per-tenant outcomes ──► threaded ✅/⚠️/❌ reply
        │   (reply carries invisible metadata: {audit_id, email})
        ▼
❌ reaction within 5 min ──► guarded rollback:
        requester-only · idempotent · time-boxed · never removes a
        suppression the bot didn't create ──► linked rollback audit row
```

### Design decisions worth noticing

- **Slack Socket Mode, not webhooks** — outbound-only WebSocket means no public endpoint, no
  firewall/SSL/DNS conversation with IT. The bot can run anywhere with internet access.
- **Multi-tenant from day one** — email systems ("tenants") are listed in a TOML config file;
  adding a brand is a config change, not a code change. Suppression lists are per-domain, which
  matches how real multi-brand companies are set up.
- **Parallel dispatch** — all tenants are called simultaneously, so the slowest system defines
  the wait, not the sum of all of them.
- **No LLM anywhere** — this is deterministic workflow automation. An LLM would add cost,
  latency, and unpredictability for zero benefit here. Not everything needs to be an AI agent.
- **Functional core, imperative shell** — every decision lives in pure, unit-testable functions;
  the Slack layer only translates events in and replies out. 96 tests, almost none of which need
  to mock Slack.
- **Audit-first ordering** — the audit row is written *before* the email system is called, so a
  crash mid-flow can never produce an action without a record. This was proven accidentally
  during development: a mid-flow failure left the audit and provider state perfectly consistent.
- **Privacy by default** — the audit database stores emails only as SHA256 hashes plus a masked
  display form (`j***@e****.com`). The rollback flow recovers the plaintext from Slack message
  metadata instead of from storage.
- **Safe rollback** — requester-only, time-boxed, idempotent (double ❌ does nothing), and it
  skips any system where the address was already suppressed before the bot acted. Over-blocking
  is recoverable; under-blocking is the real compliance risk, so the bot never guesses.

### Found-in-the-wild bugs this project caught (and now tests for)

- Slack keeps **stale `mailto:` links** when you edit a message draft — the raw text said
  `test3@…` while the screen showed `test2@…`. The parser now reads what the human saw.
- An overlong (invalid) email could match as its **truncated 64-character suffix** — a different
  address entirely. The parser now rejects it outright instead of guessing.
- Slack **scopes are not event subscriptions** — a bot can be fully authorized and still hear
  nothing. The setup guide and healthcheck now cover both.

## Tech stack

| Component | Choice | Why |
|---|---|---|
| Python 3.11 | language | typed, boring, reliable |
| slack-bolt (Socket Mode) | Slack integration | outbound-only, no public endpoint |
| httpx + respx | HTTP + test mocking | enforced timeouts, clean test story |
| Mailgun | email provider (ESP) | free tier, no signup vetting gate, per-domain suppression API |
| pydantic / pydantic-settings | config & schemas | everything validated at startup |
| SQLite (stdlib) | audit storage | zero-config, single file, queryable |
| structlog | logging | structured JSON, compliance-friendly |
| pytest | testing | 96 tests, strict red-green-refactor TDD throughout |

## Quick start

```bash
git clone <this repo> && cd slack-to-email-service-provider
python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'

cp .env.example .env              # fill in Slack tokens + Mailgun key
cp tenants.example.toml tenants.toml   # list your tenants (domains + key env var names)

.venv/bin/python scripts/healthcheck.py   # verifies every credential, prints no secrets
.venv/bin/python -m src.main              # starts the bot
```

Slack app setup (workspace, Socket Mode, **event subscriptions** — easy to miss, scopes) is
documented step-by-step in
[the build spec, Phase 0](build-spec-multi-tenant-suppression-bot.md#phase-0-test-infrastructure-setup).

Secrets hygiene: real keys live only in `.env` (gitignored); `tenants.toml` holds *names* of
environment variables, never values. A committed gitleaks pre-commit hook
(`git config core.hooksPath .githooks`) blocks accidental secret commits.

## Testing

```bash
.venv/bin/pytest                  # 96 tests, ~90% coverage
.venv/bin/ruff check src/ tests/  # lint
.venv/bin/mypy src/               # strict type checking
```

Every behavior was written test-first (red → green → refactor). HTTP is mocked with respx;
the full suppress→confirm→react→rollback lifecycle runs in integration tests against a real
SQLite file; parallelism is proven with a thread barrier, not timing assertions.

## Honest deployment status

This is a working prototype, not a production deployment. It runs end-to-end against:

- a personal Slack workspace created for development,
- a free-tier Mailgun account (sandbox domain),
- synthetic test addresses.

I built it to prove the pattern before having an internal deployment conversation. Productionizing
at a real organization would require: migration to organizational source control, a security
review, credentials via the org's secrets management, infrastructure approval, and a compliance
decision on audit-log placement (hashed vs. plaintext is a policy choice — the code defaults to
hashed).

Fun fact about real-world friction: this project originally targeted SendGrid, whose automated
onboarding compliance review rejected a fresh account with no recourse. The pivot to Mailgun cost
one config field and one thin client module — which is itself the architecture working as
intended.

## License

MIT
