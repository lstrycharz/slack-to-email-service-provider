"""Imperative shell: thin Bolt handlers translating Slack events to core calls.

All decisions live in core; this module only filters events, calls the
core, and posts replies. The reply carries invisible message metadata
({audit_id, email}) — that is how Phase 4's rollback recovers the
plaintext email without the audit DB ever storing it.
"""

from typing import Any, Protocol

from slack_bolt import App

from src.audit import AuditLog
from src.config import Settings
from src.core import build_reply_text, process_message
from src.schemas import Tenant


class ReplyPoster(Protocol):
    """The slice of Bolt's say() the shell needs."""

    def __call__(self, *, text: str, thread_ts: str, metadata: dict[str, Any]) -> None: ...


def handle_message_event(
    event: dict[str, Any],
    *,
    post_reply: ReplyPoster,
    channel_id: str,
    rollback_window_seconds: int,
    tenants: list[Tenant],
    audit: AuditLog,
    timeout: float = 10.0,
) -> None:
    """Filter a message event and run suppression for any emails in it.

    Skips: any subtype (edits would re-trigger suppression), other
    channels, and thread replies. Messages without emails get no reply —
    the channel stays quiet for normal chatter.
    """
    if event.get("subtype"):
        return
    if event.get("channel") != channel_id:
        return
    if event.get("thread_ts"):
        return
    results = process_message(
        text=event.get("text", ""),
        slack_user_id=event.get("user", ""),
        channel_id=channel_id,
        message_ts=event["ts"],
        tenants=tenants,
        audit=audit,
        timeout=timeout,
    )
    for result in results:
        post_reply(
            text=build_reply_text(result, rollback_window_seconds),
            thread_ts=event["ts"],
            metadata={
                "event_type": "suppression_action",
                "event_payload": {"audit_id": result.audit_id, "email": result.email},
            },
        )


def register_handlers(
    app: App, *, settings: Settings, tenants: list[Tenant], audit: AuditLog
) -> None:
    """Wire the shell into a Bolt app."""

    def on_message(event: dict[str, Any], say: Any) -> None:
        def post_reply(*, text: str, thread_ts: str, metadata: dict[str, Any]) -> None:
            say(text=text, thread_ts=thread_ts, metadata=metadata)

        handle_message_event(
            event,
            post_reply=post_reply,
            channel_id=settings.slack_channel_id,
            rollback_window_seconds=settings.rollback_window_seconds,
            tenants=tenants,
            audit=audit,
            timeout=settings.http_timeout_seconds,
        )

    app.event("message")(on_message)
