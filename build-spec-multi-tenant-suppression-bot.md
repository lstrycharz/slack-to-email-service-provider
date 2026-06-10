# Build Spec: Multi-Tenant Suppression Bot

> **Revision note**: This is the amended spec (v2.1, 2026-06-09). v2 incorporated a pre-build
> review that fixed two critical logic gaps (rollback email recovery, rollback of pre-existing
> suppressions), restructured the build sequence into a tracer-bullet vertical slice, made the
> functional-core/imperative-shell architecture explicit, and removed unneeded dependencies
> and scripts. v2.1 pivots the ESP from SendGrid to Mailgun after SendGrid's onboarding
> compliance review declined the free-tier account. Changelog at the bottom.

## Overview

A Slack-to-ESP suppression automation pattern: a bot listens to a designated Slack channel for
email addresses to be added to suppression lists across one or more Email Service Provider
accounts, dispatches the suppression calls in parallel, persists an audit trail, and posts a
confirmation back to Slack.

**This is a working prototype** built to demonstrate the architectural pattern for
compliance-driven multi-tenant marketing operations. The deployment in this repository runs
against a personal Slack workspace and a free-tier Mailgun account using synthetic test data.
The pattern is directly applicable to any organization running marketing communications across
multiple ESP accounts or brands where regulated suppression workflows (self-exclusion, GDPR
erasure requests, unsubscribe propagation) must complete reliably and quickly.

The system is intentionally deterministic — no LLM in the loop. The value is workflow
automation, compliance-window reduction, and a defensible audit trail.

## Honest Deployment Status

This repository contains a fully working prototype. The README, code, and demo video reflect
what's actually true:

- **Working in test environment**: Personal Slack workspace + Mailgun free tier + synthetic
  emails. End-to-end flow demonstrated.
- **Not deployed at any employer**: The architectural pattern is designed to be
  deployment-ready, but no production deployment exists. Production deployment at a real
  organization would require security review, repo migration to organizational source control,
  real credentials provisioned via that organization's secrets management, and infrastructure
  approval.
- **What this proves**: Architecture, code quality, test coverage, problem identification,
  integration patterns. Not production traffic or business impact.

This framing is intentional — interview conversations about this project should start from
honest status, not inflated claims.

## Architecture Summary

**Pattern**: Event-driven, single-process, outbound-only network. No agents, no orchestration
framework. One long-running Python process consumes Slack events via Socket Mode WebSocket,
processes each email through N parallel ESP API calls, persists an audit record, and posts a
confirmation back to Slack.

**Functional core, imperative shell.** All decision logic lives in pure functions in
`src/core.py` — `process_message(...)` and `process_rollback(...)` — which take plain data in
and return result objects out. The Slack layer (`src/slack_handlers.py`) is a thin imperative
shell: it translates Bolt events into core calls and core results into `chat.postMessage`
calls. Consequence: nearly all tests are pure-function tests plus `respx` HTTP mocks; Bolt
mocking shrinks to a handful of thin shell tests.

**Flow diagram:**

```
Slack member posts email in #suppression-requests channel
        │
        ▼
Slack Socket Mode WebSocket  ──► Bot receives message event
        │
        ├─ Has a subtype (message_changed, deleted, join, bot) ──► Ignore
        ├─ Is a thread reply ──► Ignore
        │
        ▼
Email parser (bounded regex; lowercased, deduplicated)
        │
        ├─ No valid email found ──► Ignore message, log debug
        │
        ▼
For each email found:
        │
        ├─► Write PENDING audit row (audit_id, hashed email, requester)
        │
        ├─► For each configured tenant (= Mailgun domain), in parallel:
        │       GET  /v3/{domain}/unsubscribes/{email}   (record was_already_suppressed)
        │       POST /v3/{domain}/unsubscribes
        │           │
        │           └─► Success / Failure recorded per tenant
        │
        ├─► Finalize audit row with per-tenant outcomes
        │
        ▼
Slack thread reply with status summary and audit_id
  (+ invisible message metadata: {audit_id, email} — used by rollback):
   ✅ all succeeded → "Suppressed [email] across [N] tenants. Audit: abc123.
                      React with ❌ within 5 min to rollback (requester only)."
   ⚠️ partial → "Suppressed in [X], FAILED in [Y]. Manual action required. Audit: abc123."
   ❌ all failed → "Suppression FAILED across all tenants. Audit: abc123. Investigate."
        │
        ▼
If the ORIGINAL REQUESTER reacts with ❌ within ROLLBACK_WINDOW_SECONDS:
        │
        ├─► Fetch bot reply via conversations.replies(include_all_metadata=True),
        │     read {audit_id, email} from message metadata
        ├─► Reject if: not requester / window expired / rollback already exists
        ├─► DELETE /v3/{domain}/unsubscribes/{email} for each tenant where the
        │     original succeeded AND was_already_suppressed is false
        ├─► Audit write (rollback record linked to original audit_id)
        └─► Slack reply: "Rolled back across [tenants]. Audit: <new-id> (rollback of abc123)."
```

## Technical Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Operator's primary language; rich Slack + HTTP ecosystem |
| Slack framework | `slack-bolt` v1.x with Socket Mode | Outbound WebSocket = no public endpoint, simpler IT/deployment story |
| ESP | Mailgun (free tier) | No signup vetting gate (SendGrid declined the account); per-domain suppression lists map tenant = domain; instantly usable sandbox domain |
| HTTP client | `httpx` (sync) | Modern, well-typed, timeouts enforced |
| Config | `pydantic-settings` + stdlib `tomllib` | Loads from .env + tenants.toml, validates at startup, type-safe |
| Tenant configuration | TOML file (`tenants.toml`) | Lists configured ESP accounts; easier than env vars for N-tenant cases |
| Audit storage | SQLite via stdlib `sqlite3` | Single-file, zero-config, zero-dependency, queryable |
| Logging | `structlog` | Structured JSON logs, queryable, compliance-friendly |
| Email parsing | bounded `re` regex (stdlib) | No third-party dependency; regex is the gate (`parseaddr` is too permissive to validate) |
| Process management | `tmux` for the prototype | Runs reliably on local machine for demo purposes |
| Testing | `pytest` + `respx` | respx integrates cleanly with httpx for HTTP mocking; everything is sync |

## Project Structure

```
Slack2ESP/
├── .claude/
│   ├── CLAUDE.md              # Claude Code project context
│   └── settings.json          # Security deny patterns
├── .githooks/
│   └── pre-commit             # gitleaks secret scan (enable: git config core.hooksPath .githooks)
├── .env.example               # Template with all required env vars (committed)
├── .gitignore                 # Ignores .env, *.db, data/, __pycache__, tenants.toml
├── pyproject.toml             # Pinned dependencies
├── README.md                  # Portfolio-quality README (see Demo & Portfolio section)
├── DEMO.md                    # Demo script + link to recorded walkthrough video
├── build-spec-multi-tenant-suppression-bot.md   # This document
├── tenants.example.toml       # Example tenant config (committed)
├── tenants.toml               # Real tenant config (gitignored; contains no secrets, only env var names)
├── src/
│   ├── __init__.py
│   ├── config.py              # pydantic-settings model for env vars + TOML tenant loader
│   ├── schemas.py             # Pydantic models: Tenant, TenantOutcome, SuppressionResult, RollbackResult
│   ├── email_parser.py        # Bounded regex extraction, lowercasing, dedup
│   ├── mailgun_client.py      # Thin httpx wrapper: add/remove/check suppression
│   ├── tenant_dispatch.py     # Per-tenant parallel dispatcher with per-tenant outcome tracking
│   ├── audit.py               # SQLite audit log; owns its schema (created on first connect)
│   ├── core.py                # FUNCTIONAL CORE: process_message(), process_rollback()
│   ├── slack_handlers.py      # IMPERATIVE SHELL: thin Bolt handlers, event→core→reply
│   └── main.py                # Entry point: structlog config, Bolt App, Socket Mode
├── tests/
│   ├── conftest.py            # Shared fixtures (tmp SQLite, sample tenants, respx router)
│   ├── test_config.py
│   ├── test_email_parser.py
│   ├── test_mailgun_client.py
│   ├── test_tenant_dispatch.py
│   ├── test_audit.py
│   ├── test_core.py           # The bulk of behavior tests live here
│   ├── test_slack_handlers.py # Thin: event translation + reply posting only
│   └── test_integration.py    # Full flow with mocked Slack + mocked Mailgun
├── data/
│   └── audit.db               # SQLite file (gitignored; dir kept via .gitkeep)
└── scripts/
    ├── healthcheck.py         # Verify Slack tokens + all configured ESP keys are valid
    └── demo_report.py         # Generates a demo-friendly summary from audit data
```

Removed from v1: `scripts/init_db.py` (the audit module creates its own schema on first
connect — a deep module owns its complexity, and it kills the "forgot to run init" failure
mode), `com.suppression-bot.plist` (tmux suffices for a prototype), the `handlers/` package
(replaced by the functional core + one thin shell module).

## Dependencies

`pyproject.toml` (versions current as of 2026-06-09 — re-verify before bumping):

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "multi-tenant-suppression-bot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "slack-bolt==1.28.0",
    "slack-sdk==3.42.0",
    "httpx==0.28.1",
    "pydantic==2.13.4",
    "pydantic-settings==2.14.1",
    "structlog==26.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest==9.0.3",
    "pytest-cov==7.1.0",
    "respx==0.23.1",
    "ruff==0.15.16",
    "mypy==2.1.0",
]

[tool.setuptools]
packages = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=src --cov-report=term-missing"
```

Removed from v1: `sqlite-utils` (stdlib `sqlite3` covers the ~4 queries needed), `tomli`
(dead — `requires-python >= 3.11` means stdlib `tomllib`), `pytest-asyncio` (everything is
sync; parallelism is `ThreadPoolExecutor`).

## Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token from Slack app | Yes | `xoxb-...` |
| `SLACK_APP_TOKEN` | App-Level Token (Socket Mode) | Yes | `xapp-...` |
| `SLACK_CHANNEL_ID` | Designated suppression-request channel | Yes | `C01234567` |
| `TENANTS_CONFIG_PATH` | Path to TOML file listing ESP tenants | No (default `./tenants.toml`) | `/etc/bot/tenants.toml` |
| `AUDIT_DB_PATH` | Path to SQLite audit file | No (default `./data/audit.db`) | `/var/lib/bot/audit.db` |
| `ROLLBACK_WINDOW_SECONDS` | How long after action a ❌ reaction can roll back | No (default `300`) | `300` |
| `LOG_LEVEL` | Log verbosity | No (default `INFO`) | `INFO` |
| `HTTP_TIMEOUT_SECONDS` | Per-request timeout for ESP calls | No (default `10`) | `10` |

## Tenant Configuration (`tenants.toml`)

Tenants are configured in a TOML file rather than env vars because env-var-based lists become
unwieldy at N>2. The file lists each ESP account the bot dispatches to.

`tenants.example.toml` (committed):

```toml
[[tenants]]
name = "brand_a"
display_name = "Brand A"
provider = "mailgun"
domain = "mg.brand-a.com"
api_key_env_var = "BRAND_A_MAILGUN_API_KEY"

[[tenants]]
name = "brand_b"
display_name = "Brand B"
provider = "mailgun"
domain = "mg.brand-b.com"
api_key_env_var = "BRAND_B_MAILGUN_API_KEY"
```

The real `tenants.toml` is gitignored (one canonical name — there is no `tenants.local.toml`).
API keys themselves live in env vars referenced by `api_key_env_var`. This separation means:
tenant *topology* in config, *secrets* in env. Cleaner for multi-environment setups.

Mailgun suppression lists are **per-domain**, so each tenant carries its `domain` — this is a
more realistic multi-tenant model than an account-level list: in production, brand = sending
domain = suppression list.

For the **prototype phase**, a minimum valid config is one tenant. The dispatcher code is
N-tenant from the start; the prototype just happens to run with N=1. To demonstrate the
multi-tenant case without a second Mailgun account, add a second tenant entry pointing to the
same sandbox domain and key, and document it in the demo as: "In production, each tenant has
its own domain and credentials; this demo uses one sandbox simulated as two for cost reasons."

## Phase 0 Test Infrastructure Setup

(Manual, ~15 minutes. Required before the Phase 2 tracer bullet can run live.)

**Test Slack workspace:**

1. slack.com/get-started → "Create a new workspace". Name it something neutral
   (`suppression-bot-dev`).
2. Create a channel: `#suppression-requests`.
3. api.slack.com/apps → "Create New App" → "From scratch". Name: `Suppression Bot Dev`.
4. **Socket Mode**: Settings → Socket Mode → toggle on. Generate an App-Level Token with scope
   `connections:write`. Copy the token (`xapp-...`).
5. **Event Subscriptions**: Settings → Event Subscriptions → toggle on (no request URL needed
   with Socket Mode) → "Subscribe to bot events" → add `message.channels` and
   `reaction_added` → Save. **Without this step the app connects but receives no events** —
   scopes grant permission to call APIs; event subscriptions are what make Slack push events.
6. **OAuth & Permissions** → bot token scopes: `channels:history`, `chat:write`,
   `reactions:read`, `reactions:write`.
7. Install to workspace. Copy the Bot User OAuth Token (`xoxb-...`).
8. Invite the bot: `/invite @Suppression Bot Dev` in the channel.
9. Channel ID: right-click channel → View channel details → bottom.

**Test Mailgun account:**

1. mailgun.com → sign up for the free plan (no credit card, no vetting gate — the account is
   usable immediately).
2. Your **sandbox domain** (`sandboxXXXX...mailgun.org`) is auto-provisioned. Copy its full
   name — it goes in `tenants.toml` as `domain`.
3. Dashboard → API Keys (or Settings → API Security) → copy the **private API key**.
   Free-plan keys are admin-scoped (restricted keys are a paid feature) — acceptable for a
   test account holding only synthetic data.

Note: the free plan's "authorized recipients" limit applies to *sending* only. This bot never
sends — it manages suppression lists — so the limit doesn't constrain the demo.

> History: the project originally targeted SendGrid; their onboarding compliance review
> declined the free-tier account ("unable to provide the specifics of our vetting process").
> Mailgun has no such gate. The pivot cost one config field (`domain`) and one thin client
> module — which is itself a useful demo point about the architecture.

**Test emails:** `test+1@example.com`, `test+2@example.com`, … — syntactically valid, never
deliverable, conventional test pattern. The bot adds to suppression lists; it never sends mail.

**Local environment:** copy `.env.example` to `.env`, fill in `SLACK_BOT_TOKEN`,
`SLACK_APP_TOKEN`, `SLACK_CHANNEL_ID`, and the Mailgun key env var referenced from
`tenants.toml`. Single-tenant prototype `tenants.toml`:

```toml
[[tenants]]
name = "test_brand"
display_name = "Test Brand"
provider = "mailgun"
domain = "sandboxXXXXXXXXXXXXXXXX.mailgun.org"
api_key_env_var = "TEST_BRAND_MAILGUN_API_KEY"
```

## Mailgun API Reference (endpoints verified against documentation.mailgun.com, 2026-06)

Suppression lists are per-domain; each tenant supplies its `domain`. Auth is HTTP Basic —
username `api`, password = the private API key. Base URL `https://api.mailgun.net`
(EU-region accounts use `https://api.eu.mailgun.net`; not needed for the prototype).

**Add to unsubscribe suppression list** (per domain):
- `POST https://api.mailgun.net/v3/{domain}/unsubscribes`
- Form body: `address=test@example.com`
- Success: `200 OK`
- Adding an already-suppressed address updates the existing record (no error) — which is
  exactly why the pre-check below exists.

**Check suppression status** (runtime pre-check + healthcheck):
- `GET https://api.mailgun.net/v3/{domain}/unsubscribes/{email}`
- `200` with the record if suppressed; `404` if not suppressed

**Remove from unsubscribe list** (rollback path):
- `DELETE https://api.mailgun.net/v3/{domain}/unsubscribes/{email}`
- Success: `200 OK`

> Exact status-code shapes (404-on-absent, response bodies) follow Mailgun's documented
> behavior; the Phase 2 tracer bullet confirms them live before anything depends on them.

## Workflow Logic

### Functional core (`src/core.py`)

Pure functions own all decision logic. Slack objects never cross this boundary — only plain
data and the schema models.

- `process_message(text, slack_user_id, channel_id, message_ts, tenants, ...) ->
  list[SuppressionResult]` — extracts emails, and per email: writes a `pending` audit row,
  dispatches to all tenants in parallel, finalizes the audit row with outcomes, and returns a
  result object carrying everything the shell needs to post the reply (status tier ✅/⚠️/❌,
  audit_id, per-tenant breakdown, the email for metadata).
- `process_rollback(audit_id, email, reactor_user_id, tenants, ...) -> RollbackResult` —
  validates (requester-only, window, no prior rollback), dispatches DELETEs to eligible
  tenants (original success AND not `was_already_suppressed`), writes the linked rollback
  audit row, returns the result object for the reply.

### Message shell (`src/slack_handlers.py`)

Triggered on `message` events. The shell's only logic:

1. Skip any message with a `subtype` (covers `message_changed` edits, deletions, joins, and
   `bot_message` — prevents edit-retriggering and self-loops).
2. Skip messages not in `SLACK_CHANNEL_ID`.
3. Skip thread replies (only act on top-level messages).
4. Call `core.process_message(...)`.
5. For each `SuppressionResult`, post a threaded reply with the status text AND message
   metadata: `metadata={"event_type": "suppression_action", "event_payload": {"audit_id":
   ..., "email": ...}}`. The metadata is invisible to users and is how rollback recovers the
   plaintext email without storing it in the audit DB.
6. If no valid email in the message, do nothing (keeps the channel quiet for normal chatter).

### Reaction shell (`src/slack_handlers.py`)

Triggered on `reaction_added` events:

1. Only act on the ❌ (`:x:`) emoji in `SLACK_CHANNEL_ID`.
2. `reaction_added` carries only `item.channel` + `item.ts` — fetch the reacted-to message
   via `conversations.replies(..., include_all_metadata=True)` and read
   `metadata.event_payload` → `{audit_id, email}`. If the message has no suppression
   metadata, ignore (it wasn't a bot confirmation).
3. Call `core.process_rollback(...)` — which enforces: reactor == original requester, action
   age within `ROLLBACK_WINDOW_SECONDS` (timezone-aware UTC comparison), and no existing
   rollback record for this audit_id (idempotency against double-reactions).
4. Post a threaded reply confirming rollback (or the rejection reason) with the new audit_id.

> **Metadata spike (do first in Phase 4)**: Slack docs confirm this mechanism, but one field
> report (python-slack-sdk issue #1501, enterprise workspace) saw the payload come back null.
> Before building, run a 5-minute live spike: post a message with metadata, fetch it back.
> **Fallback if the spike fails**: parse audit_id + email from the bot's reply text (the email
> is displayed there anyway, so no PII delta) — the reply format then becomes a tested contract.

## Tenant Dispatcher (`src/tenant_dispatch.py`)

`dispatch_suppression(email, tenants) -> dict[str, TenantOutcome]` and
`dispatch_removal(email, tenants) -> dict[str, TenantOutcome]`. Runs all tenant calls in
parallel via `concurrent.futures.ThreadPoolExecutor` (the codebase is sync; per-call network
wait dominates). Each `TenantOutcome` has `status` (success/failure), `was_already_suppressed`
(from the GET pre-check, add path only), `error_message` (truncated), and `duration_ms`.

Parallel dispatch is the right pattern even for N=2: it minimizes the suppression window when
one tenant's ESP is slow, and costs no meaningful complexity.

## Mailgun Client (`src/mailgun_client.py`)

Thin wrapper around `httpx.Client`. Three methods: `add_suppression(api_key, domain, email)`,
`remove_suppression(api_key, domain, email)`, `check_suppression(api_key, domain, email) ->
bool`. All:

- Use `httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)`.
- HTTP Basic auth: `("api", api_key)`.
- Catch `httpx.TimeoutException`, `httpx.HTTPError`, and unexpected statuses, raising a typed
  `MailgunError` with status_code, truncated response body, and email_hash (never the raw
  email or the key) in context. A `404` on the check endpoint is a value (not suppressed),
  not an error.
- Retry once on 5xx with 2-second backoff. No retry on 4xx.

No official Mailgun SDK — the needed surface is three endpoints; a thin httpx wrapper is more
maintainable and easier to test with respx.

## Audit Log (`src/audit.py`)

The audit module **owns its schema**: tables are created on first connect
(`CREATE TABLE IF NOT EXISTS`). No separate init script. SQLite is opened in WAL mode and
each write uses its own connection (Bolt handlers run concurrently in threads).

Table `suppression_audit`:

| Column | Type | Description |
|--------|------|-------------|
| `audit_id` | TEXT PRIMARY KEY | UUID4, surfaced in Slack reply |
| `created_at` | TEXT NOT NULL | ISO8601 UTC (timezone-aware) |
| `status` | TEXT NOT NULL | `pending` → `complete` (pending row written BEFORE dispatch) |
| `action` | TEXT NOT NULL | `add` or `remove` |
| `email_hash` | TEXT NOT NULL | SHA256 of lowercased email |
| `email_display` | TEXT NOT NULL | Masked version for human reference (e.g., `t***@e****.com`) |
| `slack_user_id` | TEXT | Who triggered (also the only user allowed to roll back) |
| `slack_channel_id` | TEXT NOT NULL | Channel where action originated |
| `slack_message_ts` | TEXT NOT NULL | Slack message timestamp |
| `tenant_outcomes` | TEXT | JSON: `{"brand_a": {"status": "success", "was_already_suppressed": false, "duration_ms": 234}, ...}` (null while pending) |
| `rollback_of` | TEXT | If this is a rollback, the audit_id of the original action |

**Ordering invariant**: the `pending` row is written *before* any ESP call, and finalized
after. There is never an ESP-side action without an audit record, even across a crash.

**On PII**: emails are SHA256-hashed (lowercased first, so lookups are case-stable) with a
masked display version. Regulator queries ("was x@y.com suppressed?") work by hashing the
query email. For a real production deployment the compliance team's preference governs —
document the decision either way.

## Error Handling

- **ESP 5xx**: retry once after 2-second backoff; then mark tenant `failure`, continue to
  other tenants, post partial-failure message.
- **ESP 4xx**: no retry (bad request / bad key). Log truncated body, mark `failure`, alert.
- **ESP timeout / network failure**: treat as 5xx.
- **Slack reconnect**: Bolt handles automatically; log reconnect events.
- **SQLite write failure**: log critical, retry once, then crash the process. If we can't
  write audit, we can't operate — the audit is the legal record.
- **All ESP calls fail**: ❌ message in Slack with audit_id. Operator attention required.
- **Partial success**: mixed ⚠️ message ("✅ brand_a / ❌ brand_b — manual action required").
- We do NOT auto-roll-back partial successes. Over-suppression is recoverable;
  under-suppression is the actual risk. (Same reasoning behind the `was_already_suppressed`
  guard: rollback must never remove a suppression the bot didn't create.)

## Security

- All secrets loaded from `.env` (gitignored). Never logged. Never committed.
- `.env.example` shows variable names with placeholder values only.
- Committed `.githooks/pre-commit` runs `gitleaks` on staged changes; enabled locally via
  `git config core.hooksPath .githooks` (documented in README).
- HTTP requests have explicit timeouts.
- Email regex is bounded (no catastrophic backtracking) — tested against ReDoS-shaped inputs.
- SQLite parameterized queries everywhere — no string interpolation.
- Audit log emails are SHA256-hashed; rollback recovers plaintext from Slack message metadata,
  not from storage.
- Rollback is requester-only and idempotent.
- `.claude/settings.json` denies reads of `.env*`, `*.pem`, `*.key`, and dangerous commands.

## Build Sequence

Chunked TDD: red → green → refactor → commit per behavior. No implementation without a failing
test first. **Phases 2–5 are vertical: Phase 2 is a tracer bullet that is live-demoable, then
each phase deepens the slice.**

### Phase 1: Scaffold

Project skeleton, pinned `pyproject.toml`, `.env.example`, `tenants.example.toml`, extended
`.gitignore`, gitleaks hook, `src/config.py` (pydantic-settings + `tomllib` tenant loader,
TDD'd), stub modules + test files. Done when: `pip install -e .[dev]`, `pytest`,
`ruff check src/`, `mypy src/` all pass. Commit as save point.

### Phase 2: Tracer bullet (minimal happy path, end-to-end)

The thinnest possible vertical slice, live-demoable at the end:
- `email_parser.extract_emails()` — happy path only (one well-formed email).
- `mailgun_client.add_suppression()` — happy path + timeout (respx).
- `tenant_dispatch` — sequential-equivalent minimal version over N tenants.
- `audit` — minimal pending→complete row.
- `core.process_message()` — happy path.
- `slack_handlers` message shell + `main.py` Socket Mode wiring.

**Exit criterion**: post `test+1@example.com` in the real test workspace → ✅ threaded reply →
address visible in the Mailgun dashboard's suppressions page (or via the GET endpoint) →
audit row queryable. (Requires Phase 0 done.)

### Phase 3: Dispatch depth

- True parallel `ThreadPoolExecutor` dispatch with `duration_ms`.
- GET pre-check → `was_already_suppressed` per tenant.
- Retry-once-on-5xx, typed `MailgunError`, no-retry-on-4xx, key/email never in errors.
- Partial-failure (⚠️) and all-failed (❌) reply tiers.
- Pending→finalize audit ordering hardened (crash-window test).

### Phase 4: Rollback

- **First: the metadata live spike** (see Workflow Logic). Pick metadata or fallback.
- Reaction shell: ❌-only, metadata lookup, ignore non-bot messages.
- `core.process_rollback()`: requester-only, UTC window check, idempotency,
  `was_already_suppressed` skip, linked rollback audit row, rollback reply.

### Phase 5: Hardening

- Parser edge cases: multiple emails, dedup, lowercasing, unicode, very long inputs,
  ReDoS-shaped strings, no-email messages.
- Subtype filtering tests (edits don't re-trigger), wrong-channel, thread replies.
- `scripts/healthcheck.py`: Slack bot token → `auth.test`; app token →
  `apps.connections.open`; each tenant's Mailgun key+domain →
  `GET /v3/{domain}/unsubscribes/healthcheck@example.invalid` (404 = key and domain valid;
  401 = bad key; other = investigate).
- `tests/test_integration.py`: full message→reply and reaction→rollback flows with mocked
  Slack client + respx.

### Phase 6: README, demo recording, presentability

This phase is what makes the prototype a credible portfolio artifact. Do not skip.

- Run the bot against the test workspace; generate ~20 events covering normal,
  partial-failure, rollback, and error cases.
- `scripts/demo_report.py` → markdown summary from audit data.
- Record 2–3 minute demo video (Loom default); script in DEMO.md.
- README per the structure below; screenshots of Slack confirmations, audit query output,
  structured log sample.

## Demo & Portfolio Considerations

The repository will be reviewed by hiring managers cold. The README is the entire
interview-before-the-interview.

### README Structure

```markdown
# Multi-Tenant Suppression Bot

A Slack-triggered automation that propagates email suppression requests across multiple ESP
accounts in parallel, with audit logging and rollback support.

**Status**: Working prototype. Built to demonstrate the architectural pattern for
compliance-driven multi-tenant marketing operations. Not currently deployed at any
organization — see [Honest Deployment Status](#honest-deployment-status).

## The Problem
[Manual workflow: 3-10 min/request, compliance window of hours-to-days. This bot closes the
window to seconds, with audit-defensible records.]

## Demo
[2-minute video walkthrough →](DEMO.md)
[Screenshots: Slack confirmation flow, audit table query]

## Architecture
[Flow diagram. Key decisions and why:]
- **Slack Socket Mode** (not webhooks): outbound-only WebSocket, no public endpoint.
- **Multi-tenant from day one**: tenants.toml config, not code.
- **Parallel dispatch**: minimizes worst-case suppression window.
- **No LLM in the loop**: deterministic workflow automation. Honest signal — not everything
  needs to be an "AI agent."
- **Functional core, imperative shell**: all decision logic is pure and unit-testable;
  Slack I/O is a thin shell.
- **Audit-first design**: pending-before-dispatch ordering; hashed emails; every rollback
  linked to its original.
- **Safe rollback**: requester-only, time-boxed, idempotent, and never removes a suppression
  the bot didn't create.

## Tech Stack
[Table: Python 3.11+, slack-bolt Socket Mode, httpx, pydantic, sqlite3, structlog,
pytest+respx]

## Quick Start
[Install, env setup, hook enable, run]

## Honest Deployment Status
[Personal workspace + free-tier Mailgun + synthetic emails. What productionizing would
require. Built to prove the pattern before an internal deployment conversation.]

## Roadmap / What I'd Build Next
- Web dashboard for the audit log
- Per-tenant rate limiting
- Slash command for suppression status lookup
- Config-driven confirm-before-act mode for high-stakes contexts
- Generic ESP adapter (SendGrid, Postmark) — deliberately not built at N=1 providers
- HRIS/IAM integration for rollback permissions

## Testing
[Coverage, how to run]

## License
MIT
```

### Demo Video Script

2–3 minutes (Loom default): problem framing (15s) → architecture (20s) → live trigger +
Mailgun suppressions-page proof (30s) → multi-tenant audit query (20s) → rollback flow (20s) →
partial-failure simulation via disabled key (20s) → code/README tour (15s). Link in DEMO.md.

## To Verify Before Building

- [x] Slack free tier supports Socket Mode and custom apps (confirmed 2026-06: free plan
  allows up to 10 third-party/custom app installs — "unlimited apps" is the paid feature.
  New workspaces show a Pro-trial upsell banner; one custom bot is fine after downgrade).
- [x] Mailgun free plan: no credit card, sandbox domain + private API key available
  immediately, no onboarding vetting gate (confirmed via Mailgun help center, 2026-06).
- [x] Mailgun unsubscribes endpoint set verified against documentation.mailgun.com (2026-06).
- [ ] Mailgun status-code shapes (404-on-absent, 200-on-delete) — confirmed live in Phase 2.
- [x] Slack message metadata round-trip — live spike PASSED 2026-06-10 (post with metadata →
  conversations.replies(include_all_metadata=True) returned the full event_payload).
  Fallback not needed.
- [ ] Demo hosting: Loom (recommended default).
- [ ] Repo visibility: private until README + DEMO are ready, then public.

## Changelog (v2 → v2.1)

- **Pivoted ESP: SendGrid → Mailgun.** SendGrid's onboarding compliance review declined the
  free-tier account at signup (opaque vetting, no recourse). Mailgun has no vetting gate, an
  instantly usable sandbox domain, and a 1:1 suppression-API mapping (add/check/remove).
  Changes: `Tenant` gains a `domain` field (Mailgun suppression lists are per-domain — a more
  realistic tenant model); auth is HTTP Basic `("api", key)` instead of Bearer;
  `sendgrid_client.py` → `mailgun_client.py`; `SendGridError` → `MailgunError`; healthcheck
  expects 404 (not 200) for a valid key. Architecture, dispatcher, audit, rollback logic:
  unchanged.

## Changelog (v1 → v2)

- **Fixed**: rollback email recovery (Slack message metadata; was unspecified and impossible
  with hash-only storage).
- **Fixed**: rollback could un-suppress pre-existing suppressions (`was_already_suppressed`
  pre-check; rollback skips those tenants).
- **Fixed**: rollback idempotency (double-reaction) + requester-only authorization.
- **Fixed**: message subtype filtering (edits no longer re-trigger).
- **Fixed**: audit row written `pending` before dispatch (no ESP action without a record).
- **Fixed**: parser gate is a bounded regex (parseaddr too permissive); emails lowercased
  before hashing.
- **Changed**: phases 2–5 restructured from horizontal layers to tracer-bullet vertical slice.
- **Changed**: functional core / imperative shell made the stated architecture;
  `handlers/` package collapsed into `core.py` + `slack_handlers.py`.
- **Changed**: dependency pins refreshed to current; `[build-system]` + package discovery added.
- **Removed**: `sqlite-utils`, `tomli`, `pytest-asyncio`, `scripts/init_db.py`, launchd plist,
  `tenants.local.toml` ambiguity.
