"""Tests for the message and reaction shells — event filtering and reply posting."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from src.audit import AuditLog
from src.schemas import Tenant, TenantOutcome
from src.slack_handlers import handle_message_event, handle_reaction_event

CHANNEL = "C456"
EMAIL = "test+1@example.com"
REQUESTER = "U123"


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


BOT_MESSAGE = {
    "ts": "1717000010.000300",
    "thread_ts": "1717000000.000100",
    "metadata": {
        "event_type": "suppression_action",
        "event_payload": {"audit_id": "orig-1", "email": EMAIL},
    },
}


def seed_add_record(audit: AuditLog) -> None:
    audit.write_pending(
        audit_id="orig-1",
        action="add",
        email=EMAIL,
        slack_user_id=REQUESTER,
        slack_channel_id=CHANNEL,
        slack_message_ts="1717000000.000100",
    )
    audit.finalize(
        "orig-1",
        {"brand_a": TenantOutcome(status="success", was_already_suppressed=False)},
    )


def make_reaction_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "reaction": "x",
        "user": REQUESTER,
        "item": {"channel": CHANNEL, "ts": BOT_MESSAGE["ts"]},
    }
    event.update(overrides)
    return event


class RecordingFetcher:
    """Stands in for conversations.replies; records lookups."""

    def __init__(self, message: dict[str, Any] | None) -> None:
        self.message = message
        self.calls: list[tuple[str, str]] = []

    def __call__(self, channel: str, ts: str) -> dict[str, Any] | None:
        self.calls.append((channel, ts))
        return self.message


def handle_reaction(
    event: dict[str, Any],
    fetcher: RecordingFetcher,
    poster: RecordingPoster,
    tenants: list[Tenant],
    audit: AuditLog,
) -> None:
    handle_reaction_event(
        event,
        fetch_message=fetcher,
        post_reply=poster,
        channel_id=CHANNEL,
        rollback_window_seconds=300,
        tenants=tenants,
        audit=audit,
    )


def test_reaction_other_emoji_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    fetcher = RecordingFetcher(BOT_MESSAGE)
    handle_reaction(make_reaction_event(reaction="thumbsup"), fetcher, poster, two_tenants, audit)
    assert (fetcher.calls, poster.replies) == ([], [])


def test_reaction_in_other_channel_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    fetcher = RecordingFetcher(BOT_MESSAGE)
    event = make_reaction_event(item={"channel": "C_OTHER", "ts": BOT_MESSAGE["ts"]})
    handle_reaction(event, fetcher, poster, two_tenants, audit)
    assert (fetcher.calls, poster.replies) == ([], [])


def test_reaction_on_message_without_suppression_metadata_is_ignored(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    fetcher = RecordingFetcher({"ts": "1.2", "text": "a normal human reply"})
    handle_reaction(make_reaction_event(), fetcher, poster, two_tenants, audit)
    assert poster.replies == []


@respx.mock
def test_reaction_on_confirmation_rolls_back_and_replies_in_thread(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    seed_add_record(audit)
    route = respx.delete(
        f"https://api.mailgun.net/v3/mg.brand-a.com/unsubscribes/{EMAIL}"
    ).mock(return_value=httpx.Response(200, json={"message": "ok"}))
    handle_reaction(make_reaction_event(), RecordingFetcher(BOT_MESSAGE), poster, two_tenants, audit)
    assert (
        route.called,
        poster.replies[0]["thread_ts"],
        "Rolled back" in poster.replies[0]["text"],
    ) == (True, "1717000000.000100", True)


def test_reaction_by_non_requester_posts_rejection(
    two_tenants: list[Tenant], audit: AuditLog, poster: RecordingPoster
) -> None:
    seed_add_record(audit)
    event = make_reaction_event(user="U_SOMEONE_ELSE")
    handle_reaction(event, RecordingFetcher(BOT_MESSAGE), poster, two_tenants, audit)
    assert "rejected" in poster.replies[0]["text"]
