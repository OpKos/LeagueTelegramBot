from __future__ import annotations

from pathlib import Path

import pytest

from league_telegram_bot.config import paths, settings


def test_build_database_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_NAME", "test_db")
    monkeypatch.setenv("DB_USER", "test_user")
    monkeypatch.setenv("DB_PASSWORD", "test_password")

    db_settings = settings.load_database_settings()
    url = settings.build_database_url(db_settings)

    assert url == "postgresql+psycopg2://test_user:test_password@db/test_db"


def test_app_path_prefers_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "config.ini"
    target.write_text("ok")

    assert paths.app_path("config.ini") == target


def test_tenhou_client_attributes() -> None:
    from league_telegram_bot.integrations.tenhou_client import TenhouClient

    client = TenhouClient(lobby="test", game_type="0009", is_enable=True)

    assert client.is_tenhou_client_enable() is True
    assert "tenhou.net" in client.start_game_url


def test_entrypoint_importable() -> None:
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("telegram")

    from league_telegram_bot import entrypoint

    assert callable(entrypoint.main)
