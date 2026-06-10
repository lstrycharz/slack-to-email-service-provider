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

# Phase 4 — Rollback ✅ COMPLETE
- [x] Metadata live spike PASSED (payload round-trips; fallback not needed)
- [x] `mailgun_client.remove_suppression()` (DELETE, same retry policy)
- [x] `core.process_rollback()`: four guards (unknown id / requester-only / idempotent / UTC window), skips was_already_suppressed≠False
- [x] Reaction shell: ❌-only, metadata lookup, ignores non-confirmation messages
- [x] Rollback audit record linked via rollback_of + rollback reply
- [x] LIVE 2026-06-10: ❌ reaction → removed from Mailgun (GET 404) → linked rollback row
      (add ecc402bd → rollback ac4847a3, 16s apart; user ran the loop twice)
- [x] BONUS live bug fixed: stale mailto hrefs after draft edits — parser now flattens
      Slack links to visible labels (what the human saw)

# Phase 5 — Hardening ✅ COMPLETE
- [x] Parser edge cases pinned: unicode surroundings, non-ASCII rejection, trailing
      punctuation, multi-email order, ReDoS-shaped + megabyte inputs. REAL BUG fixed
      red-green: overlong local part no longer matches as truncated 64-char suffix.
- [x] `scripts/healthcheck.py` — verified live: all healthy (bot token, app token, tenant)
- [x] `tests/test_integration.py`: full suppress→confirm→react→rollback lifecycle + double
      reaction + intruder rejection; mocks only at Slack-callable/HTTP boundaries
- [~] register_handlers Bolt closures stay test-uncovered (would need a faked Bolt dispatch);
      verified live across Phases 2–4 instead. Coverage 88%, gap = main.py + closures.

# Phase 6 — README + demo (NEXT)
- [ ] `scripts/demo_report.py` — markdown summary from audit data
- [ ] README per spec structure (honest status, architecture decisions, quick start)
- [ ] DEMO.md with video script; record 2–3 min video (user)
- [ ] Screenshots: Slack thread (have one), Mailgun suppressions page, audit query, log sample
- [ ] Pre-publish: rotate Mailgun key; decide repo visibility
