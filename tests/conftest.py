"""Shared fixtures: sample tenants with env-var keys set."""

import pytest

from src.schemas import Tenant


def _make_tenant(name: str, domain: str) -> Tenant:
    return Tenant(
        name=name,
        display_name=name.title(),
        provider="mailgun",
        domain=domain,
        api_key_env_var=f"{name.upper()}_MAILGUN_API_KEY",
    )


@pytest.fixture
def two_tenants(monkeypatch: pytest.MonkeyPatch) -> list[Tenant]:
    monkeypatch.setenv("BRAND_A_MAILGUN_API_KEY", "key-a")
    monkeypatch.setenv("BRAND_B_MAILGUN_API_KEY", "key-b")
    return [_make_tenant("brand_a", "mg.brand-a.com"), _make_tenant("brand_b", "mg.brand-b.com")]
