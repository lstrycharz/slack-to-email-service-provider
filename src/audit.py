"""SQLite audit log; owns its schema (created on first connect).

Emails are stored as SHA256 hashes (lowercased first, so lookups are
case-stable) plus a masked display string — never plaintext. The pending
row is written BEFORE any ESP call and finalized after; there is never an
ESP-side action without an audit record.
"""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from src.schemas import AuditRecord, TenantOutcome

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppression_audit (
    audit_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    action TEXT NOT NULL,
    email_hash TEXT NOT NULL,
    email_display TEXT NOT NULL,
    slack_user_id TEXT,
    slack_channel_id TEXT NOT NULL,
    slack_message_ts TEXT NOT NULL,
    tenant_outcomes TEXT,
    rollback_of TEXT
)
"""


def hash_email(email: str) -> str:
    """SHA256 of the lowercased address — the audit's stable email key."""
    return hashlib.sha256(email.lower().encode()).hexdigest()


def mask_email(email: str) -> str:
    """Human-readable masked form, e.g. ``t***@e****.com``."""
    local, _, domain = email.lower().partition("@")
    head, _, tld = domain.rpartition(".")
    return f"{local[:1]}***@{head[:1]}****.{tld}"


class AuditLog:
    """Append/update audit records in a single SQLite file.

    Each write opens its own connection (Bolt handlers run concurrently in
    a thread pool) and the database runs in WAL mode.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def write_pending(
        self,
        *,
        audit_id: str,
        action: Literal["add", "remove"],
        email: str,
        slack_user_id: str | None,
        slack_channel_id: str,
        slack_message_ts: str,
        rollback_of: str | None = None,
    ) -> None:
        """Record the intent to act, before any ESP call is made."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO suppression_audit (audit_id, created_at, status, action,"
                " email_hash, email_display, slack_user_id, slack_channel_id,"
                " slack_message_ts, tenant_outcomes, rollback_of)"
                " VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, NULL, ?)",
                (
                    audit_id,
                    datetime.now(UTC).isoformat(),
                    action,
                    hash_email(email),
                    mask_email(email),
                    slack_user_id,
                    slack_channel_id,
                    slack_message_ts,
                    rollback_of,
                ),
            )

    def finalize(self, audit_id: str, tenant_outcomes: dict[str, TenantOutcome]) -> None:
        """Attach per-tenant outcomes and mark the record complete."""
        payload = json.dumps({name: o.model_dump() for name, o in tenant_outcomes.items()})
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE suppression_audit SET status = 'complete', tenant_outcomes = ?"
                " WHERE audit_id = ?",
                (payload, audit_id),
            )

    def get_action(self, audit_id: str) -> AuditRecord | None:
        """Fetch one record by id, or None if it doesn't exist."""
        return self._fetch_one("SELECT * FROM suppression_audit WHERE audit_id = ?", audit_id)

    def find_rollback_of(self, audit_id: str) -> AuditRecord | None:
        """Fetch the rollback record linked to an action, if one exists.

        Used as the idempotency guard — a second ❌ reaction must not
        trigger a second rollback.
        """
        return self._fetch_one(
            "SELECT * FROM suppression_audit WHERE rollback_of = ?", audit_id
        )

    def _fetch_one(self, query: str, param: str) -> AuditRecord | None:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (param,)).fetchone()
        if row is None:
            return None
        outcomes: dict[str, TenantOutcome] | None = None
        if row["tenant_outcomes"] is not None:
            outcomes = {
                name: TenantOutcome.model_validate(data)
                for name, data in json.loads(row["tenant_outcomes"]).items()
            }
        return AuditRecord(
            audit_id=row["audit_id"],
            created_at=row["created_at"],
            status=row["status"],
            action=row["action"],
            email_hash=row["email_hash"],
            email_display=row["email_display"],
            slack_user_id=row["slack_user_id"],
            slack_channel_id=row["slack_channel_id"],
            slack_message_ts=row["slack_message_ts"],
            tenant_outcomes=outcomes,
            rollback_of=row["rollback_of"],
        )
