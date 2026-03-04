from __future__ import annotations

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def configure_logging(
    log_file: Path,
    *,
    level: int = logging.INFO,
    console_level: int = logging.INFO,
) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    root.setLevel(level)

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    logger = logging.getLogger("fileshare")
    logger.debug("Logging configured.")
    return logger
