"""Thin httpx wrapper for Mailgun per-domain unsubscribe endpoints.

Auth is HTTP Basic ("api", private key). Suppression lists are per-domain.
Error messages and exception context never include the raw email address
or the API key.
"""

import hashlib

import httpx

BASE_URL = "https://api.mailgun.net"


class MailgunError(Exception):
    """A Mailgun call failed (network, timeout, or unexpected status)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:12]


def add_suppression(api_key: str, domain: str, email: str, timeout: float = 10.0) -> None:
    """Add an address to the domain's unsubscribe suppression list.

    Adding an already-suppressed address is an idempotent update on
    Mailgun's side; callers needing to distinguish must pre-check.

    Raises:
        MailgunError: On timeout, network failure, or non-200 response.
    """
    url = f"{BASE_URL}/v3/{domain}/unsubscribes"
    try:
        response = httpx.post(
            url, data={"address": email}, auth=("api", api_key), timeout=timeout
        )
    except httpx.HTTPError as exc:
        raise MailgunError(
            f"add_suppression failed for email_hash={_email_hash(email)} "
            f"on {domain}: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise MailgunError(
            f"add_suppression unexpected status {response.status_code} "
            f"for email_hash={_email_hash(email)} on {domain}",
            status_code=response.status_code,
        )
