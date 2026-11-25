"""Configure rotating per-module logs with a consistent structured context."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shared.config import PROJECT_ROOT, cfg


class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = getattr(record, "session_id", "-")
        record.action = getattr(record, "action", record.getMessage())
        record.payload = getattr(record, "payload", "-")
        return True


def configure_logging(module_name: str) -> None:
    log_dir = Path(cfg.get("storage", {}).get("log_dir", "data/logs")).expanduser()
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s module=%(name)s "
        "session_id=%(session_id)s action=%(action)s payload=%(payload)s"
    )
    context_filter = LogContextFilter()
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / f"{module_name}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ]
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
    log_level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
    )
