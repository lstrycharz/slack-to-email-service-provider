"""Tests for email_parser — extraction happy path (edge cases come in Phase 5)."""

from src.email_parser import extract_emails


def test_extract_emails_single_address_returned() -> None:
    assert extract_emails("please suppress test+1@example.com thanks") == ["test+1@example.com"]


def test_extract_emails_no_email_returns_empty_list() -> None:
    assert extract_emails("just normal channel chatter") == []


def test_extract_emails_lowercases_address() -> None:
    assert extract_emails("suppress Test+1@Example.COM") == ["test+1@example.com"]


def test_extract_emails_uses_visible_label_not_stale_mailto_href() -> None:
    # Live bug 2026-06-10: editing a draft around an auto-linked email left
    # Slack raw text with a stale href and a split label. The user SAW
    # "test2@gmail.com"; the hrefs said test3/est2. Trust what the human sees.
    raw = "Self-exclusion request: <mailto:test3@gmail.com|t><mailto:est2@gmail.com|est2@gmail.com>"
    assert extract_emails(raw) == ["test2@gmail.com"]


def test_extract_emails_handles_plain_mailto_link_without_label() -> None:
    assert extract_emails("suppress <mailto:test+1@example.com>") == ["test+1@example.com"]


def test_extract_emails_simple_slack_link_extracts_once() -> None:
    raw = "suppress <mailto:test+1@example.com|test+1@example.com> please"
    assert extract_emails(raw) == ["test+1@example.com"]
