"""Tests for tenant_dispatch — Phase 2 minimal N-tenant dispatch with per-tenant outcomes."""

import httpx
import pytest
import respx

from src.schemas import Tenant
from src.tenant_dispatch import dispatch_suppression

EMAIL = "test+1@example.com"


@respx.mock
def test_dispatch_suppression_returns_success_outcome_per_tenant(
    two_tenants: list[Tenant],
) -> None:
    respx.post("https://api.mailgun.net/v3/mg.brand-a.com/unsubscribes").mock(
        return_value=httpx.Response(200, json={"message": "ok"})
    )
    respx.post("https://api.mailgun.net/v3/mg.brand-b.com/unsubscribes").mock(
        return_value=httpx.Response(200, json={"message": "ok"})
    )
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert [(name, o.status) for name, o in outcomes.items()] == [
        ("brand_a", "success"),
        ("brand_b", "success"),
    ]


@respx.mock
def test_dispatch_suppression_records_failure_without_stopping_other_tenants(
    two_tenants: list[Tenant],
) -> None:
    respx.post("https://api.mailgun.net/v3/mg.brand-a.com/unsubscribes").mock(
        return_value=httpx.Response(401, json={"message": "bad key"})
    )
    respx.post("https://api.mailgun.net/v3/mg.brand-b.com/unsubscribes").mock(
        return_value=httpx.Response(200, json={"message": "ok"})
    )
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert (outcomes["brand_a"].status, outcomes["brand_b"].status) == ("failure", "success")


@respx.mock
def test_dispatch_suppression_missing_api_key_env_var_is_failure_outcome(
    two_tenants: list[Tenant], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BRAND_A_MAILGUN_API_KEY")
    respx.post("https://api.mailgun.net/v3/mg.brand-b.com/unsubscribes").mock(
        return_value=httpx.Response(200, json={"message": "ok"})
    )
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert outcomes["brand_a"].status == "failure"


@respx.mock
def test_dispatch_suppression_failure_outcome_has_error_message(
    two_tenants: list[Tenant],
) -> None:
    respx.post("https://api.mailgun.net/v3/mg.brand-a.com/unsubscribes").mock(
        return_value=httpx.Response(500, json={"message": "boom"})
    )
    respx.post("https://api.mailgun.net/v3/mg.brand-b.com/unsubscribes").mock(
        return_value=httpx.Response(200, json={"message": "ok"})
    )
    outcomes = dispatch_suppression(EMAIL, two_tenants)
    assert outcomes["brand_a"].error_message is not None
