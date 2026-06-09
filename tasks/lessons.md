# Lessons

## 2026-06-09 — Third-party account vetting is a project risk, not a checkbox
SendGrid's onboarding compliance review declined a fresh free-tier account with no recourse,
after the spec's "To Verify Before Building" had only checked that the *API scope* existed on
the free tier. The unchecked assumption was account *activation* itself.
**Rule**: for any plan that depends on a third-party account, treat signup/activation as
Phase 0's first step and complete it before writing provider-specific code — or pick the
provider with no vetting gate when options are equivalent. Architecture mitigated the cost
here (thin client + provider field meant the pivot touched one module and config), which is
the second half of the lesson: keep external services behind one thin, swappable module.
