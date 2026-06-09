"""Tests for mailgun_client — Phase 2 covers add_suppression happy path + failure basics."""

import httpx
import pytest
import respx

from src.mailgun_client import MailgunError, add_suppression

DOMAIN = "mg.test-brand.com"
ADD_URL = f"https://api.mailgun.net/v3/{DOMAIN}/unsubscribes"


@respx.mock
def test_add_suppression_posts_to_domain_unsubscribes_endpoint() -> None:
    route = respx.post(ADD_URL).mock(return_value=httpx.Response(200, json={"message": "ok"}))
    add_suppression("key-123", DOMAIN, "test+1@example.com")
    assert route.called


@respx.mock
def test_add_suppression_sends_address_as_form_field() -> None:
    route = respx.post(ADD_URL).mock(return_value=httpx.Response(200, json={"message": "ok"}))
    add_suppression("key-123", DOMAIN, "test+1@example.com")
    assert b"address=test%2B1%40example.com" in route.calls.last.request.content


@respx.mock
def test_add_suppression_uses_basic_auth() -> None:
    route = respx.post(ADD_URL).mock(return_value=httpx.Response(200, json={"message": "ok"}))
    add_suppression("key-123", DOMAIN, "test+1@example.com")
    assert route.calls.last.request.headers["Authorization"].startswith("Basic ")


@respx.mock
def test_add_suppression_timeout_raises_mailgun_error() -> None:
    respx.post(ADD_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(MailgunError):
        add_suppression("key-123", DOMAIN, "test+1@example.com")


@respx.mock
def test_add_suppression_unexpected_status_raises_mailgun_error() -> None:
    respx.post(ADD_URL).mock(return_value=httpx.Response(401, json={"message": "bad key"}))
    with pytest.raises(MailgunError):
        add_suppression("key-123", DOMAIN, "test+1@example.com")


@respx.mock
def test_add_suppression_error_message_never_contains_email() -> None:
    respx.post(ADD_URL).mock(return_value=httpx.Response(401, json={"message": "bad key"}))
    with pytest.raises(MailgunError) as excinfo:
        add_suppression("key-123", DOMAIN, "test+1@example.com")
    assert "test+1@example.com" not in str(excinfo.value)
