"""Thin httpx wrapper for Mailgun per-domain unsubscribe endpoints.

Auth is HTTP Basic ("api", private key). Suppression lists are per-domain.
Retry policy: one retry after a backoff on 5xx/timeout/network errors,
never on 4xx. Error messages and exception context never include the raw
email address or the API key.
"""

import hashlib
import time

import httpx

BASE_URL = "https://api.mailgun.net"


class MailgunError(Exception):
    """A Mailgun call failed (network, timeout, or unexpected status)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:12]


def _request_with_retry(
    method: str,
    url: str,
    *,
    api_key: str,
    context: str,
    timeout: float,
    backoff_seconds: float,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    """One attempt plus one retry on 5xx/timeout/network failure.

    4xx responses return immediately (the caller decides their meaning —
    e.g. 404 on the check endpoint is a value, not an error).
    """
    for attempt in (1, 2):
        try:
            response = httpx.request(
                method, url, data=data, auth=("api", api_key), timeout=timeout
            )
        except httpx.HTTPError as exc:
            if attempt == 1:
                time.sleep(backoff_seconds)
                continue
            raise MailgunError(f"{context}: {type(exc).__name__} after retry") from exc
        if response.status_code >= 500 and attempt == 1:
            time.sleep(backoff_seconds)
            continue
        return response
    raise AssertionError("unreachable")


def add_suppression(
    api_key: str, domain: str, email: str, timeout: float = 10.0, backoff_seconds: float = 2.0
) -> None:
    """Add an address to the domain's unsubscribe suppression list.

    Adding an already-suppressed address is an idempotent update on
    Mailgun's side; callers needing to distinguish must use
    check_suppression first.

    Raises:
        MailgunError: On timeout/network failure (after one retry) or any
            non-200 response (5xx after one retry, 4xx immediately).
    """
    context = f"add_suppression for email_hash={_email_hash(email)} on {domain}"
    response = _request_with_retry(
        "POST",
        f"{BASE_URL}/v3/{domain}/unsubscribes",
        api_key=api_key,
        context=context,
        timeout=timeout,
        backoff_seconds=backoff_seconds,
        data={"address": email},
    )
    if response.status_code != 200:
        raise MailgunError(
            f"{context}: unexpected status {response.status_code}",
            status_code=response.status_code,
        )


def check_suppression(
    api_key: str, domain: str, email: str, timeout: float = 10.0, backoff_seconds: float = 2.0
) -> bool:
    """Return whether the address is on the domain's unsubscribe list.

    404 means "not suppressed" — a value, not an error.

    Raises:
        MailgunError: On timeout/network failure (after one retry) or any
            status other than 200/404.
    """
    context = f"check_suppression for email_hash={_email_hash(email)} on {domain}"
    response = _request_with_retry(
        "GET",
        f"{BASE_URL}/v3/{domain}/unsubscribes/{email}",
        api_key=api_key,
        context=context,
        timeout=timeout,
        backoff_seconds=backoff_seconds,
    )
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    raise MailgunError(
        f"{context}: unexpected status {response.status_code}",
        status_code=response.status_code,
    )
