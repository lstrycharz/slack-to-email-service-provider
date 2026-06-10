"""Settings (env vars via pydantic-settings) and the tenants.toml loader."""

import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.schemas import Tenant


def load_environment(env_file: Path = Path(".env")) -> None:
    """Export .env entries into os.environ.

    pydantic-settings reads .env only for Settings' own fields; tenant API
    keys are looked up via os.environ at dispatch time, so the file must be
    exported into the process environment too. Real env vars win over file
    values (load_dotenv does not override).
    """
    load_dotenv(env_file)


class TenantConfigError(Exception):
    """Raised when tenants.toml is missing, empty, or invalid."""


class Settings(BaseSettings):
    """Runtime configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    slack_bot_token: str
    slack_app_token: str
    slack_channel_id: str
    tenants_config_path: Path = Path("tenants.toml")
    audit_db_path: Path = Path("data/audit.db")
    rollback_window_seconds: int = 300
    log_level: str = "INFO"
    http_timeout_seconds: float = 10.0


def load_tenants(path: Path) -> list[Tenant]:
    """Parse and validate the tenant list from a TOML file.

    Args:
        path: Path to a tenants.toml file.

    Returns:
        Validated tenants, in file order.

    Raises:
        TenantConfigError: If the file is missing, defines no tenants,
            contains an invalid entry, or has duplicate tenant names.
    """
    if not path.exists():
        raise TenantConfigError(f"Tenant config not found: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    entries = data.get("tenants", [])
    if not entries:
        raise TenantConfigError(f"No tenants defined in {path}")
    try:
        tenants = [Tenant.model_validate(entry) for entry in entries]
    except ValidationError as exc:
        raise TenantConfigError(f"Invalid tenant entry in {path}: {exc}") from exc
    names = [tenant.name for tenant in tenants]
    if len(names) != len(set(names)):
        raise TenantConfigError(f"Duplicate tenant names in {path}")
    return tenants
