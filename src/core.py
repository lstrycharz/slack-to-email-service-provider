"""Functional core: all decision logic, no Slack objects.

The imperative shell (slack_handlers) translates events into these calls
and results into chat messages. process_rollback() arrives in Phase 4.
"""

import uuid
from typing import Literal

from src.audit import AuditLog
from src.email_parser import extract_emails
from src.schemas import SuppressionResult, Tenant, TenantOutcome
from src.tenant_dispatch import dispatch_suppression


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
