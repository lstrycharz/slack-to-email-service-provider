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


def test_extract_emails_multiple_addresses_in_first_seen_order() -> None:
    text = "suppress a@example.com then b@example.org then c@example.net"
    assert extract_emails(text) == ["a@example.com", "b@example.org", "c@example.net"]


def test_extract_emails_trailing_sentence_punctuation_is_dropped() -> None:
    assert extract_emails("please suppress test@example.com.") == ["test@example.com"]


def test_extract_emails_ignores_address_without_dotted_domain() -> None:
    assert extract_emails("not an email: foo@bar") == []


def test_extract_emails_does_not_truncate_overlong_local_part() -> None:
    # 70-char local part is invalid (RFC max 64). Matching a 64-char SUFFIX
    # would suppress a DIFFERENT address than the one in the message.
    text = f"suppress {'a' * 70}@example.com"
    assert extract_emails(text) == []


def test_extract_emails_unicode_surroundings_still_extract() -> None:
    assert extract_emails("zgłoszenie 🚫 wypisz test@example.com dziękuję") == ["test@example.com"]


def test_extract_emails_non_ascii_address_is_not_extracted() -> None:
    # Internationalized addresses are out of scope (deliberate): better to
    # stay silent than suppress a mis-parsed ASCII fragment of one.
    assert extract_emails("suppress żółć@example.com") == []


def test_extract_emails_redos_shaped_input_completes() -> None:
    hostile = "a@" * 20_000 + "a." * 20_000 + "@" + "." * 5_000
    assert extract_emails(hostile) == []


def test_extract_emails_huge_message_completes_with_correct_result() -> None:
    text = ("lorem ipsum " * 50_000) + " suppress test@example.com"
    assert extract_emails(text) == ["test@example.com"]
