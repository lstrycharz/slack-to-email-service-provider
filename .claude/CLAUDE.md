# Project Instructions

## Session Start

**Fresh project (no PROGRESS.md):**
Run the full test suite to orient yourself on project scope and current state. Do not proceed if tests are failing unless the task is specifically to fix them.

**Resuming work (PROGRESS.md exists):**
1. Read `.claude/PROGRESS.md` for handoff context
2. Run `git log --oneline -10` to see recent commits
3. Run the full test suite — confirm current state is green
4. Read `tasks/todo.md` and `tasks/lessons.md` if they exist
5. Pick the highest-priority incomplete item from PROGRESS.md
6. Begin work — do not re-implement anything marked as Completed

## Tech Stack
- Python 3.11 (venv at `.venv`; interpreter `/opt/homebrew/bin/python3.11`)
- slack-bolt (Socket Mode, sync) + slack-sdk
- httpx (sync) for Mailgun (Basic auth, per-domain unsubscribe lists); respx for HTTP mocking in tests
- pydantic / pydantic-settings (config), stdlib `tomllib` (tenants.toml), stdlib `sqlite3` (audit)
- structlog (JSON logs); pytest + pytest-cov, ruff, mypy --strict

## Commands
- Test: `.venv/bin/pytest`
- Lint: `.venv/bin/ruff check src/ tests/`
- Types: `.venv/bin/mypy src/`
- Run bot: `.venv/bin/python -m src.main` (needs `.env` + `tenants.toml`)
- Install: `.venv/bin/pip install -e '.[dev]'`

## Project Structure
- `build-spec-multi-tenant-suppression-bot.md` — THE spec (v2, amended). Read before any phase work.
- `src/core.py` — functional core (pure logic); `src/slack_handlers.py` — thin Bolt shell
- `src/config.py` — Settings + tenants.toml loader; `src/schemas.py` — shared pydantic models
- `src/mailgun_client.py` / `src/tenant_dispatch.py` / `src/audit.py` — HTTP, parallel dispatch, SQLite audit
- `tests/` — one file per module; `scripts/` — healthcheck + demo report; `tasks/todo.md` — phase checklist

## Rules
- Build phases are vertical slices (spec "Build Sequence") — never implement a whole layer ahead of need
- All decision logic lives in `core.py`; Slack objects never cross into the core
- No plaintext emails in the audit DB (hash + mask); rollback recovers the email from Slack message metadata
- The audit `pending` row is written BEFORE any ESP call — never break this ordering
- Secrets only via env vars named in `tenants.toml`; gitleaks hook enabled via `git config core.hooksPath .githooks`

## Definition of Done
- Tests written before implementation (red/green/refactor cycle)
- Types pass
- Tests pass
- No new linting errors
- DB migrations generated if models changed
- No `TODO` or `FIXME` left without a linked issue
- Works locally end-to-end before pushing

## Common Gotchas
- System `python3` is 3.9 — always use `.venv/bin/...`, never bare `python3`
- pytest addopts include `--cov`; add `--no-cov` for quick single-test runs
- Slack `message` events with a `subtype` (edits, joins, bot) must be ignored or edits re-trigger suppression
- Mailgun add-unsubscribe is an idempotent update (no error if already suppressed) — that's why outcomes record `was_already_suppressed`
- Mailgun GET unsubscribe returns 404 for "not suppressed" — it's a value, not an error

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Own Your Mistakes**: When wrong, say so, fix it, add a lesson. No excuses.
- **Context Is King**: Read existing code before writing new code. Match patterns already in the repo.
