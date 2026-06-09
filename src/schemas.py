"""Pydantic models shared across modules: Tenant, TenantOutcome, results."""

from typing import Literal

from pydantic import BaseModel


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
