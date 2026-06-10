# Progress — Multi-Tenant Suppression Bot

## Completed
- Build spec reviewed and amended to v2 (see changelog at bottom of
  `build-spec-multi-tenant-suppression-bot.md`) — commit aa45e2d
- Phase 1 scaffold: pinned deps (verified current 2026-06-09), examples, gitleaks hook,
  stubs — commit 262b56c
- Phase 1 config: `Settings` + `load_tenants()` + `Tenant` model, TDD'd (12 tests,
  100% cov, mypy strict clean) — commit 12899ab

## In Progress
- Phases 2, 3, AND 4 COMPLETE including live criteria (2026-06-10): full suppress + rollback
  loop demonstrated in the test workspace (add ecc402bd → ❌ reaction → rollback ac4847a3,
  Mailgun GET 404 confirms removal). Metadata spike passed; parallel dispatch proven by
  barrier test; live parser bug (stale mailto hrefs) fixed red-green.
- Next: Phase 5 hardening (see tasks/todo.md), then Phase 6 README/demo video.
- Demo-prep note: sandbox suppression list has leftover synthetic entries
  (test1, test3, est2@gmail.com) — clean or keep as demo data. Mailgun key should be
  ROTATED before any public demo (passed through chat in plaintext).

## Blocked
- Phase 2 live exit criterion needs the rest of Phase 0 (user, manual): Slack workspace
  EXISTS; still needed: Slack app + tokens, Mailgun free account (private key + sandbox
  domain) → `.env` + `tenants.toml`. Code work can proceed without it; only the live demo
  check waits.
- ESP pivot note: SendGrid declined the account at onboarding vetting (2026-06-09, ticket
  #27429538). Pivoted to Mailgun — spec v2.1.

## Next Up
1. Phase 2 tracer bullet (see `tasks/todo.md` for chunk list) — minimal happy path,
   live-demoable.
2. Phase 3 dispatch depth → Phase 4 rollback (START with metadata live spike — see spec)
   → Phase 5 hardening → Phase 6 README/demo.

## Known Issues
- None. Note for Phase 4: Slack metadata round-trip has one unconfirmed field report of
  failure (python-slack-sdk #1501); spike before building, fallback documented in spec.
