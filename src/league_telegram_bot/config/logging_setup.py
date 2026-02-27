from __future__ import annotations

import logging.config
import sys
from pathlib import Path


def configure_logging(config_path: Path) -> None:
    logging.config.fileConfig(
        config_path,
        disable_existing_loggers=False,
        defaults={"sys": sys},
        encoding="utf-8",
    )
