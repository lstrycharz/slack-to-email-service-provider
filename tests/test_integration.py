"""Full-flow integration: message → confirmation → ❌ reaction → rollback.

Mocks only at the boundaries (Slack I/O callables, Mailgun HTTP via respx);
everything between — parsing, dispatch, audit, core guards — runs for real
against a real SQLite file.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from src.audit import AuditLog
from src.schemas import Tenant
from src.slack_handlers import handle_message_event, handle_reaction_event

CHANNEL = "C456"
REQUESTER = "U123"
PARENT_TS = "1717000000.000100"
BOT_REPLY_TS = "1717000010.000300"
EMAIL = "test+1@example.com"


class FakeSlack:
    """Records bot replies and serves them back like conversations.replies."""

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []

    def post_reply(self, *, text: str, thread_ts: str, metadata: dict[str, Any]) -> None:
        self.replies.append(
            {"ts": BOT_REPLY_TS, "thread_ts": thread_ts, "text": text, "metadata": metadata}
        )

    def fetch_message(self, channel: str, ts: str) -> dict[str, Any] | None:
        return next((r for r in self.replies if r["ts"] == ts), None)


@pytest.fixture
def slack() -> FakeSlack:
    return FakeSlack()


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "audit.db")


def mock_mailgun(domain: str) -> dict[str, respx.Route]:
    base = f"https://api.mailgun.net/v3/{domain}/unsubscribes"
    return {
        "check": respx.get(f"{base}/{EMAIL}").mock(
            return_value=httpx.Response(404, json={})
        ),
        "add": respx.post(base).mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        ),
        "remove": respx.delete(f"{base}/{EMAIL}").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        ),
    }


def post_suppression_message(
    slack: FakeSlack, tenants: list[Tenant], audit: AuditLog
) -> None:
    handle_message_event(
        {
            "type": "message",
            "channel": CHANNEL,
            "user": REQUESTER,
            "text": f"Self-exclusion request: <mailto:{EMAIL}|{EMAIL}>",
            "ts": PARENT_TS,
        },
        post_reply=slack.post_reply,
        channel_id=CHANNEL,
        rollback_window_seconds=300,
        tenants=tenants,
        audit=audit,
    )


def react_with_x(
    slack: FakeSlack, tenants: list[Tenant], audit: AuditLog, user: str = REQUESTER
) -> None:
    handle_reaction_event(
        {"reaction": "x", "user": user, "item": {"channel": CHANNEL, "ts": BOT_REPLY_TS}},
        fetch_message=slack.fetch_message,
        post_reply=slack.post_reply,
        channel_id=CHANNEL,
        rollback_window_seconds=300,
        tenants=tenants,
        audit=audit,
    )


@respx.mock
def test_full_lifecycle_suppress_confirm_react_rollback(
    two_tenants: list[Tenant], slack: FakeSlack, audit: AuditLog
) -> None:
    routes_a = mock_mailgun("mg.brand-a.com")
    routes_b = mock_mailgun("mg.brand-b.com")

    post_suppression_message(slack, two_tenants, audit)
    confirmation = slack.replies[0]
    audit_id = confirmation["metadata"]["event_payload"]["audit_id"]

    react_with_x(slack, two_tenants, audit)
    rollback_reply = slack.replies[1]

    add_record = audit.get_action(audit_id)
    rollback_record = audit.find_rollback_of(audit_id)
    assert add_record is not None and add_record.status == "complete"
    assert rollback_record is not None and rollback_record.action == "remove"
    assert routes_a["remove"].called and routes_b["remove"].called
    assert "✅" in confirmation["text"] and "Rolled back" in rollback_reply["text"]
    assert rollback_reply["thread_ts"] == PARENT_TS


@respx.mock
def test_second_reaction_is_rejected_as_already_rolled_back(
    two_tenants: list[Tenant], slack: FakeSlack, audit: AuditLog
) -> None:
    mock_mailgun("mg.brand-a.com")
    mock_mailgun("mg.brand-b.com")
    post_suppression_message(slack, two_tenants, audit)
    react_with_x(slack, two_tenants, audit)
    react_with_x(slack, two_tenants, audit)
    assert "already rolled back" in slack.replies[2]["text"]


@respx.mock
def test_reaction_by_other_user_does_not_remove_anything(
    two_tenants: list[Tenant], slack: FakeSlack, audit: AuditLog
) -> None:
    routes_a = mock_mailgun("mg.brand-a.com")
    mock_mailgun("mg.brand-b.com")
    post_suppression_message(slack, two_tenants, audit)
    react_with_x(slack, two_tenants, audit, user="U_INTRUDER")
    assert routes_a["remove"].called is False and "rejected" in slack.replies[1]["text"]