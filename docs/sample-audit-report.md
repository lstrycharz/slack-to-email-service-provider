# Suppression Audit Report

- Total audited actions: **11** (8 suppressions, 3 rollbacks)
- Per-tenant calls: **11**, success rate **100%**
- Median tenant call duration: **992 ms**

| When (UTC) | Action | Email (masked) | Status | Tenant outcomes | Rollback of |
|---|---|---|---|---|---|
| 2026-06-10T00:34:57 | add | t***@g****.com | complete | test_brand: success | — |
| 2026-06-10T00:38:42 | add | t***@g****.com | complete | test_brand: success | — |
| 2026-06-10T00:54:01 | add | t***@g****.com | complete | test_brand: success (1139ms) | — |
| 2026-06-10T00:54:02 | add | e***@g****.com | complete | test_brand: success (992ms) | — |
| 2026-06-10T00:59:15 | add | t***@g****.com | complete | test_brand: success (1155ms) | — |
| 2026-06-10T00:59:26 | remove | t***@g****.com | complete | test_brand: success (538ms) | fa4a8a27-245d-478f-b80b-dd3ee488a88a |
| 2026-06-10T01:00:07 | add | t***@g****.com | complete | test_brand: success (755ms) | — |
| 2026-06-10T01:00:23 | remove | t***@g****.com | complete | test_brand: success (369ms) | ecc402bd-aefb-4e92-80fe-aacc10ecf011 |
| 2026-06-10T01:08:05 | add | t***@g****.com | complete | test_brand: success (1018ms) | — |
| 2026-06-10T01:08:27 | add | t***@h****.com | complete | test_brand: success (998ms) | — |
| 2026-06-10T01:09:17 | remove | t***@h****.com | complete | test_brand: success (537ms) | 00ea6131-54cb-40e9-b70b-7401b1e10f4c |

_Emails are stored as SHA256 hashes with masked display values — this report contains no PII._
