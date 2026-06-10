"""Per-tenant parallel dispatcher with per-tenant outcome tracking.

All tenants run concurrently in a ThreadPoolExecutor — the per-call
network wait dominates, and parallelism minimizes the worst-case
suppression window when one tenant's ESP is slow.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor

from src.mailgun_client import (
    MailgunError,
    add_suppression,
    check_suppression,
    remove_suppression,
)
from src.schemas import Tenant, TenantOutcome


def dispatch_suppression(
    email: str, tenants: list[Tenant], timeout: float = 10.0, backoff_seconds: float = 2.0
) -> dict[str, TenantOutcome]:
    """Add the email to every tenant's suppression list, in parallel.

    One tenant's failure never stops the others; each failure is captured
    as a TenantOutcome rather than raised.

    Returns:
        Outcomes keyed by tenant name, in tenant order.
    """
    with ThreadPoolExecutor(max_workers=max(len(tenants), 1)) as pool:
        futures = {
            tenant.name: pool.submit(_suppress_one, email, tenant, timeout, backoff_seconds)
            for tenant in tenants
        }
        return {name: future.result() for name, future in futures.items()}


def dispatch_removal(
    email: str, tenants: list[Tenant], timeout: float = 10.0, backoff_seconds: float = 2.0
) -> dict[str, TenantOutcome]:
    """Remove the email from every given tenant's suppression list, in parallel.

    Rollback path: the caller is responsible for passing only eligible
    tenants (original add succeeded AND was_already_suppressed is False).

    Returns:
        Outcomes keyed by tenant name, in tenant order.
    """
    with ThreadPoolExecutor(max_workers=max(len(tenants), 1)) as pool:
        futures = {
            tenant.name: pool.submit(_remove_one, email, tenant, timeout, backoff_seconds)
            for tenant in tenants
        }
        return {name: future.result() for name, future in futures.items()}


def _remove_one(
    email: str, tenant: Tenant, timeout: float, backoff_seconds: float
) -> TenantOutcome:
    started = time.perf_counter()
    api_key = os.environ.get(tenant.api_key_env_var)
    if not api_key:
        outcome = TenantOutcome(
            status="failure", error_message=f"env var {tenant.api_key_env_var} is not set"
        )
    else:
        try:
            remove_suppression(
                api_key, tenant.domain, email, timeout=timeout, backoff_seconds=backoff_seconds
            )
            outcome = TenantOutcome(status="success")
        except MailgunError as exc:
            outcome = TenantOutcome(status="failure", error_message=str(exc))
    outcome.duration_ms = int((time.perf_counter() - started) * 1000)
    return outcome


def _suppress_one(
    email: str, tenant: Tenant, timeout: float, backoff_seconds: float
) -> TenantOutcome:
    started = time.perf_counter()

    def done(outcome: TenantOutcome) -> TenantOutcome:
        outcome.duration_ms = int((time.perf_counter() - started) * 1000)
        return outcome

    api_key = os.environ.get(tenant.api_key_env_var)
    if not api_key:
        return done(
            TenantOutcome(
                status="failure",
                error_message=f"env var {tenant.api_key_env_var} is not set",
            )
        )
    was_already_suppressed = _pre_check(api_key, tenant, email, timeout, backoff_seconds)
    try:
        add_suppression(
            api_key, tenant.domain, email, timeout=timeout, backoff_seconds=backoff_seconds
        )
    except MailgunError as exc:
        return done(
            TenantOutcome(
                status="failure",
                error_message=str(exc),
                was_already_suppressed=was_already_suppressed,
            )
        )
    return done(
        TenantOutcome(status="success", was_already_suppressed=was_already_suppressed)
    )


def _pre_check(
    api_key: str, tenant: Tenant, email: str, timeout: float, backoff_seconds: float
) -> bool | None:
    """Was the address suppressed before we acted? None if unknowable.

    A pre-check failure must not block the suppression itself —
    under-suppression is the real risk, not a missing data point.
    """
    try:
        return check_suppression(
            api_key, tenant.domain, email, timeout=timeout, backoff_seconds=backoff_seconds
        )
    except MailgunError:
        return None
