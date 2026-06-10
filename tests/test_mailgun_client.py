"""Tests for mailgun_client — add/check suppression, retry-once-on-5xx semantics."""

import httpx
import pytest
import respx

from src.mailgun_client import MailgunError, add_suppression, check_suppression

DOMAIN = "mg.test-brand.com"
ADD_URL = f"https://api.mailgun.net/v3/{DOMAIN}/unsubscribes"
CHECK_URL = f"{ADD_URL}/test+1@example.com"


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
def test_add_suppression_timeout_twice_raises_mailgun_error() -> None:
    respx.post(ADD_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(MailgunError):
        add_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)


@respx.mock
def test_add_suppression_retries_once_on_5xx_then_succeeds() -> None:
    route = respx.post(ADD_URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"message": "ok"})]
    )
    add_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)
    assert route.call_count == 2


@respx.mock
def test_add_suppression_5xx_twice_raises_after_one_retry() -> None:
    route = respx.post(ADD_URL).mock(side_effect=[httpx.Response(500), httpx.Response(503)])
    with pytest.raises(MailgunError):
        add_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)
    assert route.call_count == 2


@respx.mock
def test_add_suppression_4xx_is_not_retried() -> None:
    route = respx.post(ADD_URL).mock(return_value=httpx.Response(401, json={"message": "no"}))
    with pytest.raises(MailgunError):
        add_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)
    assert route.call_count == 1


@respx.mock
def test_add_suppression_timeout_then_success_recovers() -> None:
    route = respx.post(ADD_URL).mock(
        side_effect=[httpx.TimeoutException("slow"), httpx.Response(200, json={"message": "ok"})]
    )
    add_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)
    assert route.call_count == 2


@respx.mock
def test_check_suppression_returns_true_when_present() -> None:
    respx.get(CHECK_URL).mock(
        return_value=httpx.Response(200, json={"address": "test+1@example.com"})
    )
    assert check_suppression("key-123", DOMAIN, "test+1@example.com") is True


@respx.mock
def test_check_suppression_returns_false_when_absent() -> None:
    respx.get(CHECK_URL).mock(return_value=httpx.Response(404, json={"message": "not found"}))
    assert check_suppression("key-123", DOMAIN, "test+1@example.com") is False


@respx.mock
def test_check_suppression_unexpected_status_raises_mailgun_error() -> None:
    respx.get(CHECK_URL).mock(return_value=httpx.Response(401, json={"message": "bad key"}))
    with pytest.raises(MailgunError):
        check_suppression("key-123", DOMAIN, "test+1@example.com", backoff_seconds=0)


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
