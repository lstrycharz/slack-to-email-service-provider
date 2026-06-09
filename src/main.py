"""Entry point: structlog config, Bolt App, Socket Mode start."""

import logging

import structlog
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.audit import AuditLog
from src.config import Settings, load_tenants
from src.slack_handlers import register_handlers


def configure_logging(level: str) -> None:
    """Structured JSON logs — queryable, compliance-friendly."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
    )


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger()
    tenants = load_tenants(settings.tenants_config_path)
    audit = AuditLog(settings.audit_db_path)
    app = App(token=settings.slack_bot_token)
    register_handlers(app, settings=settings, tenants=tenants, audit=audit)
    log.info(
        "starting socket mode",
        tenants=[t.name for t in tenants],
        channel=settings.slack_channel_id,
    )
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()  # type: ignore[no-untyped-call]  # slack_bolt ships start() unannotated


if __name__ == "__main__":
    main()
