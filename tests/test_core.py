"""Tests for core.process_message, process_rollback, and reply formatting."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from src.audit import AuditLog
from src.core import (
    build_reply_text,
    build_rollback_reply_text,
    process_message,
    process_rollback,
)
from src.schemas import RollbackResult, SuppressionResult, Tenant, TenantOutcome


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


EMAIL = "test+1@example.com"
REQUESTER = "U123"


def seed_add_record(
    audit: AuditLog,
    audit_id: str = "orig-1",
    outcomes: dict[str, TenantOutcome] | None = None,
) -> None:
    audit.write_pending(
        audit_id=audit_id,
        action="add",
        email=EMAIL,
        slack_user_id=REQUESTER,
        slack_channel_id="C456",
        slack_message_ts="1717000000.000100",
    )
    audit.finalize(
        audit_id,
        outcomes
        or {
            "brand_a": TenantOutcome(status="success", was_already_suppressed=False),
            "brand_b": TenantOutcome(status="success", was_already_suppressed=False),
        },
    )


def rollback(
    audit: AuditLog,
    tenants: list[Tenant],
    audit_id: str = "orig-1",
    reactor: str = REQUESTER,
    now: datetime | None = None,
) -> RollbackResult:
    return process_rollback(
        audit_id=audit_id,
        email=EMAIL,
        reactor_user_id=reactor,
        tenants=tenants,
        audit=audit,
        rollback_window_seconds=300,
        now=now,
    )


def mock_remove(domain: str, status_code: int = 200) -> respx.Route:
    return respx.delete(f"https://api.mailgun.net/v3/{domain}/unsubscribes/{EMAIL}").mock(
        return_value=httpx.Response(status_code, json={"message": "ok"})
    )


def test_rollback_unknown_audit_id_is_rejected(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    result = rollback(audit, two_tenants, audit_id="nope")
    assert result.accepted is False and "unknown" in str(result.reject_reason)


def test_rollback_by_non_requester_is_rejected(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    seed_add_record(audit)
    result = rollback(audit, two_tenants, reactor="U_SOMEONE_ELSE")
    assert result.accepted is False and "requester" in str(result.reject_reason)


def test_rollback_after_window_is_rejected(two_tenants: list[Tenant], audit: AuditLog) -> None:
    seed_add_record(audit)
    late = datetime.now(UTC) + timedelta(seconds=400)
    result = rollback(audit, two_tenants, now=late)
    assert result.accepted is False and "window" in str(result.reject_reason)


@respx.mock
def test_rollback_twice_is_rejected_second_time(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    seed_add_record(audit)
    mock_remove("mg.brand-a.com")
    mock_remove("mg.brand-b.com")
    rollback(audit, two_tenants)
    result = rollback(audit, two_tenants)
    assert result.accepted is False and "already" in str(result.reject_reason)


@respx.mock
def test_rollback_success_writes_linked_audit_record(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    seed_add_record(audit)
    mock_remove("mg.brand-a.com")
    mock_remove("mg.brand-b.com")
    result = rollback(audit, two_tenants)
    record = audit.find_rollback_of("orig-1")
    assert (
        result.accepted,
        result.status,
        record is not None and record.audit_id == result.rollback_audit_id,
    ) == (True, "success", True)


@respx.mock
def test_rollback_skips_tenants_suppressed_before_the_action(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    seed_add_record(
        audit,
        outcomes={
            "brand_a": TenantOutcome(status="success", was_already_suppressed=True),
            "brand_b": TenantOutcome(status="success", was_already_suppressed=False),
        },
    )
    route_a = mock_remove("mg.brand-a.com")
    mock_remove("mg.brand-b.com")
    result = rollback(audit, two_tenants)
    assert (route_a.called, result.skipped_tenants) == (False, ["brand_a"])


def test_rollback_with_nothing_eligible_makes_no_calls(
    two_tenants: list[Tenant], audit: AuditLog
) -> None:
    # was_already_suppressed=None (unknown prior state) must also be skipped:
    # deleting could remove a suppression the bot didn't create.
    seed_add_record(
        audit,
        outcomes={
            "brand_a": TenantOutcome(status="success", was_already_suppressed=None),
            "brand_b": TenantOutcome(status="failure"),
        },
    )
    result = rollback(audit, two_tenants)  # no respx mock: any HTTP call would error
    assert result.accepted is True and result.outcomes == {}


def test_rollback_reply_text_rejected_includes_reason() -> None:
    result = RollbackResult(
        original_audit_id="orig-1", email=EMAIL, accepted=False, reject_reason="window expired"
    )
    assert "window expired" in build_rollback_reply_text(result)


def test_rollback_reply_text_success_includes_rollback_audit_id() -> None:
    result = RollbackResult(
        original_audit_id="orig-1",
        email=EMAIL,
        accepted=True,
        rollback_audit_id="rb-9",
        status="success",
        outcomes={"brand_b": TenantOutcome(status="success")},
    )
    assert "rb-9" in build_rollback_reply_text(result)
