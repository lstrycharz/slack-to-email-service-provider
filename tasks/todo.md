# Phase 1 — Scaffold

## Done when
- [ ] Amended spec committed as `build-spec-multi-tenant-suppression-bot.md`
- [ ] `pip install -e .[dev]` succeeds in a Python 3.11 venv
- [ ] `pytest` runs green (config loader tests, written red-first)
- [ ] `ruff check src/` and `mypy src/` pass clean
- [ ] `.env.example`, `tenants.example.toml`, gitleaks pre-commit hook in place; `.gitignore` covers `.env`, `*.db`, `data/`, `tenants.toml`
- [ ] `.claude/CLAUDE.md` placeholder sections populated; everything committed as save points

## Steps
- [x] Write amended spec into repo
- [ ] Extend .gitignore (data/, *.db, tenants.toml)
- [ ] pyproject.toml with current pinned deps + build-system
- [ ] Directory tree + stub modules + stub test files
- [ ] .env.example, tenants.example.toml, .githooks/pre-commit (gitleaks)
- [ ] venv (python3.11) + pip install -e .[dev]
- [ ] RED: tests/test_config.py (Settings + load_tenants) — confirm failing
- [ ] GREEN: src/config.py + src/schemas.py Tenant model — tests pass
- [ ] ruff + mypy clean
- [ ] Populate .claude/CLAUDE.md (Tech Stack, Commands, Structure, Rules, Session Start)
- [ ] Commits: spec → scaffold → config TDD → CLAUDE.md

## Next up (later phases)
Phase 2 tracer bullet (needs Phase 0 manual setup: Slack workspace + SendGrid account → tokens in .env).
