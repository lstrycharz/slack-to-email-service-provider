"""Tests for core.process_message and reply formatting."""

import sqlite3
from pathlib import Path

import httpx
import pytest
import respx

from src.audit import AuditLog
from src.core import build_reply_text, process_message
from src.schemas import SuppressionResult, Tenant, TenantOutcome


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "audit.db")


def mock_domain(domain: str, status_code: int = 200) -> None:
    respx.route(method="GET", url__startswith=f"https://api.mailgun.net/v3/{domain}/").mock(
        return_value=httpx.Response(404, json={})
    )
    respx.post(f"https://api.mailgun.net/v3/{domain}/unsubscribes").mock(
        return_value=httpx.Response(status_code, json={"message": "ok"})
    )


def run(text: str, tenants: list[Tenant], audit: AuditLog) -> list[SuppressionResult]:
    return process_message(
        text=text,
        slack_user_id="U123",
        channel_id="C456",
        message_ts="1717000000.000100",
        tenants=tenants,
        audit=audit,
    )


@respx.mock
def test_process_message_returns_one_result_per_email(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    mock_domain("mg.brand-a.com")
    mock_domain("mg.brand-b.com")
    results = run("suppress test+1@example.com and test+2@example.com", two_tenants, audit)
    assert [r.email for r in results] == ["test+1@example.com", "test+2@example.com"]


def test_process_message_without_emails_returns_empty_list(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    assert run("normal channel chatter", two_tenants, audit) == []


@respx.mock
def test_process_message_all_tenants_succeed_gives_success_status(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    mock_domain("mg.brand-a.com")
    mock_domain("mg.brand-b.com")
    results = run("suppress test+1@example.com", two_tenants, audit)
    assert results[0].status == "success"


@respx.mock
def test_process_message_mixed_outcomes_gives_partial_status(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    mock_domain("mg.brand-a.com", status_code=401)
    mock_domain("mg.brand-b.com")
    results = run("suppress test+1@example.com", two_tenants, audit)
    assert results[0].status == "partial"


@respx.mock
def test_process_message_all_tenants_fail_gives_failure_status(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    mock_domain("mg.brand-a.com", status_code=500)
    mock_domain("mg.brand-b.com", status_code=500)
    results = run("suppress test+1@example.com", two_tenants, audit)
    assert results[0].status == "failure"


@respx.mock
def test_process_message_finalizes_audit_record(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    mock_domain("mg.brand-a.com")
    mock_domain("mg.brand-b.com")
    results = run("suppress test+1@example.com", two_tenants, audit)
    record = audit.get_action(results[0].audit_id)
    assert record is not None and record.status == "complete"


def test_crash_during_dispatch_leaves_pending_audit_row(
    two_tenants: list[Tenant], audit: AuditLog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The audit invariant: the pending row is written BEFORE any ESP call,
    # so even an unexpected crash mid-dispatch leaves a record of intent.
    def boom(*args: object, **kwargs: object) -> dict[str, TenantOutcome]:
        raise RuntimeError("simulated crash mid-dispatch")

    monkeypatch.setattr("src.core.dispatch_suppression", boom)
    with pytest.raises(RuntimeError):
        run("suppress test+1@example.com", two_tenants, audit)
    conn = sqlite3.connect(tmp_path / "audit.db")
    count = conn.execute(
        "SELECT COUNT(*) FROM suppression_audit WHERE status = 'pending'"
    ).fetchone()[0]
    assert count == 1


def make_result(status: str, outcomes: dict[str, TenantOutcome]) -> SuppressionResult:
    return SuppressionResult(
        email="test+1@example.com", audit_id="abc123", status=status, outcomes=outcomes
    )


def test_build_reply_text_success_contains_email_and_audit_id() -> None:
    result = make_result("success", {"brand_a": TenantOutcome(status="success")})
    text = build_reply_text(result, rollback_window_seconds=300)
    assert "test+1@example.com" in text and "abc123" in text


def test_build_reply_text_partial_names_failed_tenant() -> None:
    result = make_result(
        "partial",
        {
            "brand_a": TenantOutcome(status="success"),
            "brand_b": TenantOutcome(status="failure", error_message="boom"),
        },
    )
    assert "brand_b" in build_reply_text(result, rollback_window_seconds=300)


def test_build_reply_text_failure_says_failed() -> None:
    result = make_result("failure", {"brand_a": TenantOutcome(status="failure")})
    assert "FAILED" in build_reply_text(result, rollback_window_seconds=300)
