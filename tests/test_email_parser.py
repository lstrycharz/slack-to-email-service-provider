"""Tests for email_parser — extraction happy path (edge cases come in Phase 5)."""

from src.email_parser import extract_emails


def test_extract_emails_single_address_returned() -> None:
    assert extract_emails("please suppress test+1@example.com thanks") == ["test+1@example.com"]


def test_extract_emails_no_email_returns_empty_list() -> None:
    assert extract_emails("just normal channel chatter") == []


def test_extract_emails_lowercases_address() -> None:
    assert extract_emails("suppress Test+1@Example.COM") == ["test+1@example.com"]
