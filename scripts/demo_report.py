"""Generate a markdown summary of the audit log for demos and reviews.

Reads only what the audit stores — hashed/masked emails, never plaintext.

Usage: .venv/bin/python scripts/demo_report.py [path/to/audit.db]
"""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def render_report(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM suppression_audit ORDER BY created_at").fetchall()
    conn.close()

    adds = [r for r in rows if r["action"] == "add"]
    rollbacks = [r for r in rows if r["rollback_of"]]
    durations = []
    tenant_success = 0
    tenant_total = 0
    for row in rows:
        outcomes = json.loads(row["tenant_outcomes"]) if row["tenant_outcomes"] else {}
        for outcome in outcomes.values():
            tenant_total += 1
            if outcome.get("status") == "success":
                tenant_success += 1
            if outcome.get("duration_ms") is not None:
                durations.append(outcome["duration_ms"])

    lines = [
        "# Suppression Audit Report",
        "",
        f"- Total audited actions: **{len(rows)}** "
        f"({len(adds)} suppressions, {len(rollbacks)} rollbacks)",
        f"- Per-tenant calls: **{tenant_total}**, success rate "
        f"**{(100 * tenant_success / tenant_total):.0f}%**" if tenant_total else "- No calls yet",
        f"- Median tenant call duration: **{sorted(durations)[len(durations) // 2]} ms**"
        if durations
        else "- No duration data",
        "",
        "| When (UTC) | Action | Email (masked) | Status | Tenant outcomes | Rollback of |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        outcomes = json.loads(row["tenant_outcomes"]) if row["tenant_outcomes"] else {}
        summary = ", ".join(
            f"{name}: {o['status']}"
            + (f" ({o['duration_ms']}ms)" if o.get("duration_ms") is not None else "")
            for name, o in outcomes.items()
        )
        lines.append(
            f"| {row['created_at'][:19]} | {row['action']} | {row['email_display']} "
            f"| {row['status']} | {summary} | {row['rollback_of'] or '—'} |"
        )
    lines.append("")
    lines.append("_Emails are stored as SHA256 hashes with masked display values — "
                 "this report contains no PII._")
    return "\n".join(lines)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/audit.db"
    print(render_report(path))
