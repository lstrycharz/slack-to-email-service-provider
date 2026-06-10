"""Tests for config: Settings env loading and the tenants.toml loader."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings, TenantConfigError, load_environment, load_tenants
from src.schemas import Tenant

REQUIRED_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_APP_TOKEN": "xapp-test",
    "SLACK_CHANNEL_ID": "C0TEST",
}

VALID_TENANTS_TOML = """\
[[tenants]]
name = "brand_a"
display_name = "Brand A"
provider = "mailgun"
domain = "mg.brand-a.com"
api_key_env_var = "BRAND_A_MAILGUN_API_KEY"

[[tenants]]
name = "brand_b"
display_name = "Brand B"
provider = "mailgun"
domain = "mg.brand-b.com"
api_key_env_var = "BRAND_B_MAILGUN_API_KEY"
"""


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def make_settings() -> Settings:
    return Settings(_env_file=None)


def write_toml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "tenants.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_settings_missing_required_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        make_settings()


def test_settings_reads_slack_channel_id(required_env: None) -> None:
    assert make_settings().slack_channel_id == "C0TEST"


def test_settings_default_rollback_window_is_300(required_env: None) -> None:
    assert make_settings().rollback_window_seconds == 300


def test_settings_default_audit_db_path(required_env: None) -> None:
    assert make_settings().audit_db_path == Path("data/audit.db")


def test_settings_env_overrides_rollback_window(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROLLBACK_WINDOW_SECONDS", "60")
    assert make_settings().rollback_window_seconds == 60


def test_load_tenants_valid_file_returns_tenants_in_order(tmp_path: Path) -> None:
    tenants = load_tenants(write_toml(tmp_path, VALID_TENANTS_TOML))
    assert [t.name for t in tenants] == ["brand_a", "brand_b"]


def test_load_tenants_parses_all_tenant_fields(tmp_path: Path) -> None:
    tenants = load_tenants(write_toml(tmp_path, VALID_TENANTS_TOML))
    assert tenants[0] == Tenant(
        name="brand_a",
        display_name="Brand A",
        provider="mailgun",
        domain="mg.brand-a.com",
        api_key_env_var="BRAND_A_MAILGUN_API_KEY",
    )


def test_load_tenants_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(TenantConfigError, match="not found"):
        load_tenants(tmp_path / "nope.toml")


def test_load_tenants_empty_tenant_list_raises(tmp_path: Path) -> None:
    with pytest.raises(TenantConfigError, match="No tenants"):
        load_tenants(write_toml(tmp_path, "# empty\n"))


def test_load_tenants_duplicate_names_raises(tmp_path: Path) -> None:
    duplicated = VALID_TENANTS_TOML.replace('"brand_b"', '"brand_a"', 1)
    with pytest.raises(TenantConfigError, match="Duplicate"):
        load_tenants(write_toml(tmp_path, duplicated))


def test_load_tenants_unknown_provider_raises(tmp_path: Path) -> None:
    bad_provider = VALID_TENANTS_TOML.replace('provider = "mailgun"', 'provider = "sendgrid"', 1)
    with pytest.raises(TenantConfigError, match="Invalid tenant"):
        load_tenants(write_toml(tmp_path, bad_provider))


def test_load_tenants_missing_domain_raises(tmp_path: Path) -> None:
    missing_domain = VALID_TENANTS_TOML.replace('domain = "mg.brand-a.com"\n', "", 1)
    with pytest.raises(TenantConfigError, match="Invalid tenant"):
        load_tenants(write_toml(tmp_path, missing_domain))


def test_load_environment_exports_env_file_vars_to_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tenant API keys live in .env but are read via os.environ — they must
    # be exported, not just parsed into Settings fields.
    monkeypatch.delenv("SOME_TENANT_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TENANT_KEY=key-value\n", encoding="utf-8")
    load_environment(env_file)
    assert os.environ.get("SOME_TENANT_KEY") == "key-value"


def test_load_tenants_missing_field_raises(tmp_path: Path) -> None:
    missing_field = VALID_TENANTS_TOML.replace('display_name = "Brand A"\n', "", 1)
    with pytest.raises(TenantConfigError, match="Invalid tenant"):
        load_tenants(write_toml(tmp_path, missing_field))
