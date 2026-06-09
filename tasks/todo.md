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
- [ ] LIVE exit criterion: post test+1@example.com → ✅ reply → visible in Mailgun suppressions → audit row queryable
      (waits on user's Phase 0: Slack app tokens + Mailgun account; smoke check passed —
      `python -m src.main` fails cleanly naming missing env vars)
