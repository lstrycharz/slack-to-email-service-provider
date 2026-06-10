"""Tests for tenant_dispatch — parallel N-tenant dispatch, pre-check, per-tenant outcomes."""

import threading

import httpx
import pytest
import respx

from src.schemas import Tenant
from src.tenant_dispatch import dispatch_suppression

EMAIL = "test+1@example.com"
DOMAIN_A = "mg.brand-a.com"
DOMAIN_B = "mg.brand-b.com"


def mock_check(domain: str, status_code: int = 404) -> respx.Route:
    return respx.get(f"https://api.mailgun.net/v3/{domain}/unsubscribes/{EMAIL}").mock(
        return_value=httpx.Response(status_code, json={})
    )


def mock_add(domain: str, status_code: int = 200) -> respx.Route:
    return respx.post(f"https://api.mailgun.net/v3/{domain}/unsubscribes").mock(
        return_value=httpx.Response(status_code, json={"message": "ok"})
    )


def mock_tenant_ok(domain: str) -> None:
    mock_check(domain)
    mock_add(domain)


@respx.mock
def test_dispatch_suppression_returns_success_outcome_per_tenant(
    two_tenants: list[Tenant],
) -> None:
    mock_tenant_ok(DOMAIN_A)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert [(name, o.status) for name, o in outcomes.items()] == [
        ("brand_a", "success"),
        ("brand_b", "success"),
    ]


@respx.mock
def test_dispatch_suppression_records_failure_without_stopping_other_tenants(
    two_tenants: list[Tenant],
) -> None:
    mock_check(DOMAIN_A)
    mock_add(DOMAIN_A, status_code=401)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert (outcomes["brand_a"].status, outcomes["brand_b"].status) == ("failure", "success")


@respx.mock
def test_dispatch_suppression_missing_api_key_env_var_is_failure_outcome(
    two_tenants: list[Tenant], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BRAND_A_MAILGUN_API_KEY")
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert outcomes["brand_a"].status == "failure"


@respx.mock
def test_dispatch_suppression_failure_outcome_has_error_message(
    two_tenants: list[Tenant],
) -> None:
    mock_check(DOMAIN_A)
    mock_add(DOMAIN_A, status_code=500)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants, backoff_seconds=0)
    assert outcomes["brand_a"].error_message is not None


@respx.mock
def test_dispatch_records_not_already_suppressed_when_precheck_404(
    two_tenants: list[Tenant],
) -> None:
    mock_tenant_ok(DOMAIN_A)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert outcomes["brand_a"].was_already_suppressed is False


@respx.mock
def test_dispatch_records_already_suppressed_when_precheck_200(
    two_tenants: list[Tenant],
) -> None:
    mock_check(DOMAIN_A, status_code=200)
    mock_add(DOMAIN_A)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert outcomes["brand_a"].was_already_suppressed is True


@respx.mock
def test_dispatch_precheck_error_leaves_already_suppressed_unknown_but_proceeds(
    two_tenants: list[Tenant],
) -> None:
    mock_check(DOMAIN_A, status_code=401)
    mock_add(DOMAIN_A)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants, backoff_seconds=0)
    assert (outcomes["brand_a"].status, outcomes["brand_a"].was_already_suppressed) == (
        "success",
        None,
    )


@respx.mock
def test_dispatch_outcomes_carry_duration_ms(two_tenants: list[Tenant]) -> None:
    mock_tenant_ok(DOMAIN_A)
    mock_tenant_ok(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert all(o.duration_ms is not None and o.duration_ms >= 0 for o in outcomes.values())


@respx.mock
def test_dispatch_runs_tenants_in_parallel(two_tenants: list[Tenant]) -> None:
    # Both pre-checks block on a shared barrier: the call only completes if
    # both tenants are in flight simultaneously. Sequential dispatch would
    # deadlock and break the barrier (test failure) instead of passing.
    barrier = threading.Barrier(2, timeout=5)

    def blocking_check(request: httpx.Request) -> httpx.Response:
        barrier.wait()
        return httpx.Response(404, json={})

    respx.get(f"https://api.mailgun.net/v3/{DOMAIN_A}/unsubscribes/{EMAIL}").mock(
        side_effect=blocking_check
    )
    respx.get(f"https://api.mailgun.net/v3/{DOMAIN_B}/unsubscribes/{EMAIL}").mock(
        side_effect=blocking_check
    )
    mock_add(DOMAIN_A)
    mock_add(DOMAIN_B)
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert all(o.status == "success" for o in outcomes.values())
