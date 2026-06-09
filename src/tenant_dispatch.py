"""Per-tenant dispatcher with per-tenant outcome tracking.

Phase 2: sequential minimal version. Phase 3 swaps the loop body into a
ThreadPoolExecutor and adds the was_already_suppressed pre-check — the
public signature stays the same.
"""

import os

from src.mailgun_client import MailgunError, add_suppression
from src.schemas import Tenant, TenantOutcome


def dispatch_suppression(
    email: str, tenants: list[Tenant], timeout: float = 10.0
) -> dict[str, TenantOutcome]:
    """Add the email to every tenant's suppression list.

    One tenant's failure never stops the others; each failure is captured
    as a TenantOutcome rather than raised.

    Returns:
        Outcomes keyed by tenant name, in tenant order.
    """
    outcomes: dict[str, TenantOutcome] = {}
    for tenant in tenants:
        outcomes[tenant.name] = _suppress_one(email, tenant, timeout)
    return outcomes


def _suppress_one(email: str, tenant: Tenant, timeout: float) -> TenantOutcome:
    api_key = os.environ.get(tenant.api_key_env_var)
    if not api_key:
        return TenantOutcome(
            status="failure",
            error_message=f"env var {tenant.api_key_env_var} is not set",
        )
    try:
        add_suppression(api_key, tenant.domain, email, timeout=timeout)
    except MailgunError as exc:
        return TenantOutcome(status="failure", error_message=str(exc))
    return TenantOutcome(status="success")
