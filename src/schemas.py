"""Pydantic models shared across modules: Tenant, TenantOutcome, results."""

from typing import Literal

from pydantic import BaseModel


class Tenant(BaseModel):
    """One ESP account the bot dispatches suppressions to."""

    name: str
    display_name: str
    provider: Literal["sendgrid"]
    api_key_env_var: str
