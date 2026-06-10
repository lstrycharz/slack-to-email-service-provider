"""Pydantic models shared across modules: Tenant, TenantOutcome, results."""

from typing import Literal

from pydantic import BaseModel


class TenantOutcome(BaseModel):
    """Result of one tenant's suppression call.

    was_already_suppressed comes from the pre-dispatch GET check: True
    means the address was on the list before we acted (rollback must skip
    this tenant — we'd be removing a suppression we didn't create); None
    means the pre-check itself failed and the prior state is unknown.
    """

    status: Literal["success", "failure"]
    error_message: str | None = None
    was_already_suppressed: bool | None = None
    duration_ms: int | None = None


class SuppressionResult(BaseModel):
    """Outcome of one email's suppression run across all tenants."""

    email: str
    audit_id: str
    status: Literal["success", "partial", "failure"]
    outcomes: dict[str, TenantOutcome]


class RollbackResult(BaseModel):
    """Outcome of a ❌-reaction rollback attempt.

    accepted=False means a guard rejected it (unknown id, wrong user,
    expired window, already rolled back) and nothing was dispatched.
    skipped_tenants were eligible-looking but had was_already_suppressed
    True or unknown — removing those could delete a suppression the bot
    didn't create.
    """

    original_audit_id: str
    email: str
    accepted: bool
    reject_reason: str | None = None
    rollback_audit_id: str | None = None
    status: Literal["success", "partial", "failure"] | None = None
    outcomes: dict[str, TenantOutcome] | None = None
    skipped_tenants: list[str] = []


class AuditRecord(BaseModel):
    """One row of the suppression audit trail."""

    audit_id: str
    created_at: str
    status: Literal["pending", "complete"]
    action: Literal["add", "remove"]
    email_hash: str
    email_display: str
    slack_user_id: str | None
    slack_channel_id: str
    slack_message_ts: str
    tenant_outcomes: dict[str, TenantOutcome] | None = None
    rollback_of: str | None = None


class Tenant(BaseModel):
    """One ESP account the bot dispatches suppressions to.

    Mailgun suppression lists are per-domain, so each tenant carries the
    domain its unsubscribe list lives under.
    """

    name: str
    display_name: str
    provider: Literal["mailgun"]
    domain: str
    api_key_env_var: str
