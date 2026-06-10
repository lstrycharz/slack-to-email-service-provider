# Phase 1 — Scaffold ✅ COMPLETE

## Done when
- [x] Amended spec committed as `build-spec-multi-tenant-suppression-bot.md`
- [x] `pip install -e .[dev]` succeeds in a Python 3.11 venv
- [x] `pytest` runs green (config loader tests, written red-first — 12 passed, 100% cov)
- [x] `ruff check src/` and `mypy src/` pass clean
- [x] `.env.example`, `tenants.example.toml`, gitleaks pre-commit hook in place; `.gitignore` covers `.env`, `*.db`, `data/`, `tenants.toml`
- [x] `.claude/CLAUDE.md` placeholder sections populated; everything committed as save points

## Review
Three save-point commits: spec v2 (aa45e2d) → scaffold (262b56c) → config TDD (12899ab).
Red step verified (ImportError before implementation). gitleaks hook active via
`core.hooksPath .githooks` and scanned all three commits.

# Phase 2 — Tracer bullet (NEXT)

Blocked on Phase 0 (manual, see spec): Slack workspace EXISTS — still needed: Slack app
(Socket Mode, scopes: channels:history, chat:write, reactions:read, reactions:write),
Mailgun free account (private API key + sandbox domain name), fill `.env` + `tenants.toml`.

## Steps (each red → green → commit)
- [x] `email_parser.extract_emails()` — happy path only (6d6470e)
- [x] `mailgun_client.add_suppression()` — happy path + timeout (d9b1b75)
- [x] `tenant_dispatch` — minimal N-tenant loop (20f48a9)
- [x] `audit` — pending→complete row, schema on first connect (f53b1a3)
- [x] `core.process_message()` — happy path (dfc6cd5)
- [x] `slack_handlers` message shell + `main.py` Socket Mode wiring (4785aa6)
- [x] LIVE exit criterion MET 2026-06-10: posted test1@gmail.com in #suppression-requests →
      ✅ threaded reply (audit bb923bbc-bb1f-43f8-a0d1-3f3367c80121) → address confirmed on
      Mailgun suppression list (GET 200) → audit row complete with success outcome.
      Live-confirmed along the way: Mailgun 404-on-absent, idempotent re-add, and the
      pending-before-dispatch invariant surviving a mid-flow crash (missing-scope reply
      failure left audit + ESP state consistent).

# Phase 3 — Dispatch depth ✅ COMPLETE
- [x] Parallel ThreadPoolExecutor dispatch + duration_ms (barrier test proves concurrency)
- [x] GET pre-check → was_already_suppressed per tenant (None on pre-check failure, proceeds)
- [x] Retry-once-on-5xx/timeout with backoff; no retry on 4xx
- [x] Partial-failure (⚠️) and all-failed (❌) tiers covered through dispatcher in core tests
- [x] Pending→finalize crash-window regression test

# Phase 4 — Rollback (NEXT)
- [ ] FIRST: metadata live spike (post w/ metadata → fetch via conversations.replies(include_all_metadata=True))
- [ ] `mailgun_client.remove_suppression()` (DELETE)
- [ ] `core.process_rollback()`: requester-only, UTC window, idempotency, skip was_already_suppressed≠False
- [ ] Reaction shell: ❌-only, metadata lookup, ignore non-bot messages
- [ ] Rollback audit record linked via rollback_of + rollback reply
- [ ] LIVE: ❌ on a fresh confirmation → removed from Mailgun → rollback audit row
