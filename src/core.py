"""Functional core: all decision logic, no Slack objects.

The imperative shell (slack_handlers) translates events into these calls
and results into chat messages. process_rollback() arrives in Phase 4.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from src.audit import AuditLog
from src.email_parser import extract_emails
from src.schemas import RollbackResult, SuppressionResult, Tenant, TenantOutcome
from src.tenant_dispatch import dispatch_removal, dispatch_suppression


def process_message(
    *,
    text: str,
    slack_user_id: str,
    channel_id: str,
    message_ts: str,
    tenants: list[Tenant],
    audit: AuditLog,
    timeout: float = 10.0,
) -> list[SuppressionResult]:
    """Suppress every email found in a message across all tenants.

    Per email: write a pending audit row, dispatch to all tenants, finalize
    the row with per-tenant outcomes. The pending-before-dispatch ordering
    is the audit invariant — never reorder it.

    Returns:
        One result per extracted email; empty list if the text has none.
    """
    results: list[SuppressionResult] = []
    for email in extract_emails(text):
        audit_id = str(uuid.uuid4())
        audit.write_pending(
            audit_id=audit_id,
            action="add",
            email=email,
            slack_user_id=slack_user_id,
            slack_channel_id=channel_id,
            slack_message_ts=message_ts,
        )
        outcomes = dispatch_suppression(email, tenants, timeout=timeout)
        audit.finalize(audit_id, outcomes)
        results.append(
            SuppressionResult(
                email=email,
                audit_id=audit_id,
                status=_status_tier(outcomes),
                outcomes=outcomes,
            )
        )
    return results


def _status_tier(
    outcomes: dict[str, TenantOutcome],
) -> Literal["success", "partial", "failure"]:
    statuses = {outcome.status for outcome in outcomes.values()}
    if statuses == {"success"}:
        return "success"
    if statuses == {"failure"}:
        return "failure"
    return "partial"


def process_rollback(
    *,
    audit_id: str,
    email: str,
    reactor_user_id: str,
    tenants: list[Tenant],
    audit: AuditLog,
    rollback_window_seconds: int,
    timeout: float = 10.0,
    backoff_seconds: float = 2.0,
    now: datetime | None = None,
) -> RollbackResult:
    """Roll back a suppression action, guarded four ways.

    Rejects when: the audit id is unknown / not an add action, the reactor
    isn't the original requester, a rollback already exists (double
    reactions), or the window has expired. Only tenants where the original
    add succeeded AND the address was verifiably NOT suppressed beforehand
    are removed — unknown prior state is treated as "do not touch".
    """

    def rejected(reason: str) -> RollbackResult:
        return RollbackResult(
            original_audit_id=audit_id, email=email, accepted=False, reject_reason=reason
        )

    record = audit.get_action(audit_id)
    if record is None or record.action != "add":
        return rejected("unknown audit id")
    if reactor_user_id != record.slack_user_id:
        return rejected("only the original requester can roll back")
    if audit.find_rollback_of(audit_id) is not None:
        return rejected("already rolled back")
    age = (now or datetime.now(UTC)) - datetime.fromisoformat(record.created_at)
    if age > timedelta(seconds=rollback_window_seconds):
        return rejected("rollback window expired")

    original_outcomes = record.tenant_outcomes or {}
    eligible_names = {
        name
        for name, outcome in original_outcomes.items()
        if outcome.status == "success" and outcome.was_already_suppressed is False
    }
    skipped = [
        name
        for name, outcome in original_outcomes.items()
        if outcome.status == "success" and name not in eligible_names
    ]
    eligible_tenants = [t for t in tenants if t.name in eligible_names]

    rollback_id = str(uuid.uuid4())
    audit.write_pending(
        audit_id=rollback_id,
        action="remove",
        email=email,
        slack_user_id=reactor_user_id,
        slack_channel_id=record.slack_channel_id,
        slack_message_ts=record.slack_message_ts,
        rollback_of=audit_id,
    )
    outcomes = dispatch_removal(
        email, eligible_tenants, timeout=timeout, backoff_seconds=backoff_seconds
    )
    audit.finalize(rollback_id, outcomes)
    return RollbackResult(
        original_audit_id=audit_id,
        email=email,
        accepted=True,
        rollback_audit_id=rollback_id,
        status=_status_tier(outcomes) if outcomes else "success",
        outcomes=outcomes,
        skipped_tenants=skipped,
    )


def build_reply_text(result: SuppressionResult, rollback_window_seconds: int) -> str:
    """Render the Slack confirmation for one suppression result."""
    minutes = rollback_window_seconds // 60
    if result.status == "success":
        return (
            f"✅ Suppressed {result.email} across {len(result.outcomes)} tenant(s). "
            f"Audit: {result.audit_id}. "
            f"React with ❌ within {minutes} min to roll back (requester only)."
        )
    succeeded = [n for n, o in result.outcomes.items() if o.status == "success"]
    failed = [n for n, o in result.outcomes.items() if o.status == "failure"]
    if result.status == "partial":
        return (
            f"⚠️ Suppressed {result.email} in {', '.join(succeeded)} — "
            f"FAILED in {', '.join(failed)}. Manual action required. "
            f"Audit: {result.audit_id}."
        )
    return (
        f"❌ Suppression of {result.email} FAILED across all tenants. "
        f"Audit: {result.audit_id}. Investigate."
    )


def build_rollback_reply_text(result: RollbackResult) -> str:
    """Render the Slack reply for a rollback attempt."""
    if not result.accepted:
        return (
            f"🚫 Rollback rejected: {result.reject_reason}. "
            f"Audit: {result.original_audit_id}."
        )
    skipped_note = (
        f" Skipped (suppressed before the action): {', '.join(result.skipped_tenants)}."
        if result.skipped_tenants
        else ""
    )
    outcomes = result.outcomes or {}
    if not outcomes:
        return (
            f"↩️ Nothing to roll back for {result.email} — no tenant had a removable "
            f"suppression.{skipped_note} Audit: {result.rollback_audit_id} "
            f"(rollback of {result.original_audit_id})."
        )
    if result.status == "success":
        return (
            f"↩️ Rolled back {result.email} across {len(outcomes)} tenant(s)."
            f"{skipped_note} Audit: {result.rollback_audit_id} "
            f"(rollback of {result.original_audit_id})."
        )
    failed = [name for name, o in outcomes.items() if o.status == "failure"]
    return (
        f"⚠️ Rollback of {result.email} FAILED in {', '.join(failed)} — manual action "
        f"required.{skipped_note} Audit: {result.rollback_audit_id} "
        f"(rollback of {result.original_audit_id})."
    )
