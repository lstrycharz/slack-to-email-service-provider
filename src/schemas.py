"""Pydantic models shared across modules: Tenant, TenantOutcome, results."""

from typing import Literal

from pydantic import BaseModel


class TenantOutcome(BaseModel):
    """Result of one tenant's suppression call."""

    status: Literal["success", "failure"]
    error_message: str | None = None


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
