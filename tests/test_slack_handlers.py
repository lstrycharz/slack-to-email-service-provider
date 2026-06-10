"""Tests for the message shell — event filtering and reply posting (thin by design)."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from src.audit import AuditLog
from src.schemas import Tenant
from src.slack_handlers import handle_message_event

CHANNEL = "C456"


class RecordingPoster:
    """Stands in for Bolt's say(); records every reply."""

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []

    def __call__(self, *, text: str, thread_ts: str, metadata: dict[str, Any]) -> None:
        self.replies.append({"text": text, "thread_ts": thread_ts, "metadata": metadata})


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "audit.db")


@pytest.fixture
def poster() -> RecordingPoster:
    return RecordingPoster()


def make_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "message",
        "channel": CHANNEL,
        "user": "U123",
        "text": "suppress test+1@example.com",
        "ts": "1717000000.000100",
    }
    event.update(overrides)
    return event


def handle(
    event: dict[str, Any],
    poster: RecordingPoster,
    tenants: list[Tenant],
    audit: AuditLog,
) -> None:
    handle_message_event(
        event,
        post_reply=poster,
        channel_id=CHANNEL,
        rollback_window_seconds=300,
        tenants=tenants,
        audit=audit,
    )


def mock_both_domains() -> None:
    for domain in ("mg.brand-a.com", "mg.brand-b.com"):
        respx.route(
            method="GET", url__startswith=f"https://api.mailgun.net/v3/{domain}/"
        ).mock(return_value=httpx.Response(404, json={}))
        respx.post(f"https://api.mailgun.net/v3/{domain}/unsubscribes").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )


@respx.mock
def test_valid_message_posts_threaded_reply(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    mock_both_domains()
    handle(make_event(), poster, two_tenants, audit)
    assert poster.replies[0]["thread_ts"] == "1717000000.000100"


@respx.mock
def test_valid_message_reply_metadata_carries_audit_id_and_email(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    mock_both_domains()
    handle(make_event(), poster, two_tenants, audit)
    payload = poster.replies[0]["metadata"]["event_payload"]
    assert payload["email"] == "test+1@example.com" and payload["audit_id"]


def test_message_with_subtype_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    handle(make_event(subtype="message_changed"), poster, two_tenants, audit)
    assert poster.replies == []


def test_message_in_other_channel_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    handle(make_event(channel="C_OTHER"), poster, two_tenants, audit)
    assert poster.replies == []


def test_thread_reply_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    handle(make_event(thread_ts="1716999999.000001"), poster, two_tenants, audit)
    assert poster.replies == []


def test_message_without_email_posts_nothing(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    handle(make_event(text="hello team"), poster, two_tenants, audit)
    assert poster.replies == []
