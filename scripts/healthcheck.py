"""Verify every credential the bot needs, without printing any secret.

Checks: Slack bot token (auth.test), Slack app token
(apps.connections.open), and each tenant's Mailgun key + domain (GET on a
sentinel address — 404 proves the key and domain are valid and the
sentinel is absent). Exit code 0 = all healthy, 1 = something failed.

Usage: .venv/bin/python scripts/healthcheck.py
"""

import os
import sys

import httpx
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Settings, load_environment, load_tenants  # noqa: E402
from src.schemas import Tenant  # noqa: E402

SENTINEL = "healthcheck@example.invalid"


def check_slack_bot_token(settings: Settings) -> bool:
    try:
        response = WebClient(token=settings.slack_bot_token).auth_test()
    except SlackApiError as exc:
        print(f"  FAIL slack bot token: {exc.response['error']}")
        return False
    print(f"  ok   slack bot token (team={response['team']}, bot={response['user']})")
    return True


def check_slack_app_token(settings: Settings) -> bool:
    try:
        WebClient().apps_connections_open(app_token=settings.slack_app_token)
    except SlackApiError as exc:
        print(f"  FAIL slack app token: {exc.response['error']}")
        return False
    print("  ok   slack app token (socket mode connection grantable)")
    return True


def check_tenant(tenant: Tenant, timeout: float) -> bool:
    api_key = os.environ.get(tenant.api_key_env_var)
    if not api_key:
        print(f"  FAIL tenant {tenant.name}: env var {tenant.api_key_env_var} is not set")
        return False
    url = f"https://api.mailgun.net/v3/{tenant.domain}/unsubscribes/{SENTINEL}"
    try:
        response = httpx.get(url, auth=("api", api_key), timeout=timeout)
    except httpx.HTTPError as exc:
        print(f"  FAIL tenant {tenant.name}: {type(exc).__name__}")
        return False
    if response.status_code == 404:
        print(f"  ok   tenant {tenant.name} ({tenant.domain})")
        return True
    if response.status_code in (200,):
        print(f"  WARN tenant {tenant.name}: sentinel address is suppressed (unexpected but key valid)")
        return True
    print(f"  FAIL tenant {tenant.name}: status {response.status_code} (401 = bad key)")
    return False


def main() -> int:
    load_environment()
    settings = Settings()
    tenants = load_tenants(settings.tenants_config_path)
    print(f"healthcheck: {len(tenants)} tenant(s) configured")
    results = [
        check_slack_bot_token(settings),
        check_slack_app_token(settings),
        *(check_tenant(t, settings.http_timeout_seconds) for t in tenants),
    ]
    healthy = all(results)
    print("healthy" if healthy else "UNHEALTHY")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
