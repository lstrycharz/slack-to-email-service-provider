"""Imperative shell: thin Bolt handlers translating Slack events to core calls.

All decisions live in core; this module only filters events, calls the
core, and posts replies. The reply carries invisible message metadata
({audit_id, email}) — that is how Phase 4's rollback recovers the
plaintext email without the audit DB ever storing it.
"""

from typing import Any, Protocol

from slack_bolt import App
from slack_sdk import WebClient

from src.audit import AuditLog
from src.config import Settings
from src.core import (
    build_reply_text,
    build_rollback_reply_text,
    process_message,
    process_rollback,
)
from src.schemas import Tenant


class ReplyPoster(Protocol):
    """The slice of Bolt's say() the shell needs."""

    def __call__(self, *, text: str, thread_ts: str, metadata: dict[str, Any]) -> None: ...


class MessageFetcher(Protocol):
    """Fetch one message (with metadata) by channel + ts, None if unavailable."""

    def __call__(self, channel: str, ts: str) -> dict[str, Any] | None: ...


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


def handle_reaction_event(
    event: dict[str, Any],
    *,
    fetch_message: MessageFetcher,
    post_reply: ReplyPoster,
    channel_id: str,
    rollback_window_seconds: int,
    tenants: list[Tenant],
    audit: AuditLog,
    timeout: float = 10.0,
) -> None:
    """❌ on a bot confirmation triggers a guarded rollback.

    The confirmation's message metadata carries {audit_id, email} — that
    is how the plaintext email is recovered without the audit DB storing
    it. Reactions on anything without that metadata are ignored.
    """
    if event.get("reaction") != "x":
        return
    item = event.get("item", {})
    if item.get("channel") != channel_id:
        return
    message = fetch_message(channel_id, item.get("ts", ""))
    if not message:
        return
    metadata = message.get("metadata") or {}
    if metadata.get("event_type") != "suppression_action":
        return
    payload = metadata.get("event_payload", {})
    result = process_rollback(
        audit_id=payload.get("audit_id", ""),
        email=payload.get("email", ""),
        reactor_user_id=event.get("user", ""),
        tenants=tenants,
        audit=audit,
        rollback_window_seconds=rollback_window_seconds,
        timeout=timeout,
    )
    post_reply(
        text=build_rollback_reply_text(result),
        thread_ts=message.get("thread_ts") or message.get("ts", ""),
        metadata={},
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

    def on_reaction(event: dict[str, Any], say: Any, client: WebClient) -> None:
        def fetch_message(channel: str, ts: str) -> dict[str, Any] | None:
            response = client.conversations_replies(
                channel=channel, ts=ts, include_all_metadata=True, limit=1
            )
            messages = response.get("messages") or []
            return messages[0] if messages else None

        def post_reply(*, text: str, thread_ts: str, metadata: dict[str, Any]) -> None:
            say(text=text, thread_ts=thread_ts)

        handle_reaction_event(
            event,
            fetch_message=fetch_message,
            post_reply=post_reply,
            channel_id=settings.slack_channel_id,
            rollback_window_seconds=settings.rollback_window_seconds,
            tenants=tenants,
            audit=audit,
            timeout=settings.http_timeout_seconds,
        )

    app.event("message")(on_message)
    app.event("reaction_added")(on_reaction)
