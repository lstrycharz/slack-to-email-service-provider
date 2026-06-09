"""Tests for audit — Phase 2 covers the pending→complete lifecycle and PII hygiene."""

import hashlib
from pathlib import Path

import pytest

from src.audit import AuditLog
from src.schemas import TenantOutcome

EMAIL = "Test+1@Example.com"


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "nested" / "audit.db")


def write_pending(audit: AuditLog, audit_id: str = "aud-1") -> str:
    audit.write_pending(
        audit_id=audit_id,
        action="add",
        email=EMAIL,
        slack_user_id="U123",
        slack_channel_id="C456",
        slack_message_ts="1717000000.000100",
    )
    return audit_id


def test_write_pending_then_get_action_returns_pending_record(audit: AuditLog) -> None:
    audit_id = write_pending(audit)
    record = audit.get_action(audit_id)
    assert record is not None and record.status == "pending"


def test_audit_stores_sha256_of_lowercased_email(audit: AuditLog) -> None:
    audit_id = write_pending(audit)
    record = audit.get_action(audit_id)
    assert record is not None
    assert record.email_hash == hashlib.sha256(EMAIL.lower().encode()).hexdigest()


def test_audit_never_stores_plaintext_email(audit: AuditLog, tmp_path: Path) -> None:
    write_pending(audit)
    raw = b"".join(  # WAL mode: fresh writes may live in the -wal sidecar, scan everything
        f.read_bytes() for f in (tmp_path / "nested").iterdir() if f.is_file()
    )
    assert EMAIL.lower().encode() not in raw.lower()


def test_finalize_marks_record_complete_with_outcomes(audit: AuditLog) -> None:
    audit_id = write_pending(audit)
    audit.finalize(audit_id, {"brand_a": TenantOutcome(status="success")})
    record = audit.get_action(audit_id)
    assert record is not None and record.status == "complete"


def test_finalize_roundtrips_tenant_outcomes(audit: AuditLog) -> None:
    audit_id = write_pending(audit)
    outcomes = {
        "brand_a": TenantOutcome(status="success"),
        "brand_b": TenantOutcome(status="failure", error_message="boom"),
    }
    audit.finalize(audit_id, outcomes)
    record = audit.get_action(audit_id)
    assert record is not None and record.tenant_outcomes == outcomes


def test_get_action_unknown_id_returns_none(audit: AuditLog) -> None:
    assert audit.get_action("nope") is None
