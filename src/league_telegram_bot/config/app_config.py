from __future__ import annotations

import configparser
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import app_path
from .settings import build_database_url, load_database_settings


@dataclass(frozen=True)
class AppConfig:
    lobby: str
    chat: str
    admin_chat: str
    database_url: str
    config_path: Path
    locales_path: Path
    token_path: Path
    logging_config_path: Path


def load_app_config() -> AppConfig:
    config_path = app_path("config.ini")
    parser = configparser.ConfigParser()
    parser.read(config_path)

    lobby = parser.get("Settings", "lobby")
    chat = parser.get("Settings", "chat")
    admin_chat = parser.get("Settings", "admin_chat")
    database_url = build_database_url(load_database_settings())

    return AppConfig(
        lobby=lobby,
        chat=chat,
        admin_chat=admin_chat,
        database_url=database_url,
        config_path=config_path,
        locales_path=app_path("locales.json"),
        token_path=app_path("token.txt"),
        logging_config_path=app_path("logging.ini"),
    )


def load_locales(locales_path: Path) -> dict[str, dict[str, str]]:
    with open(locales_path, encoding="utf-8") as handle:
        return json.load(handle)
