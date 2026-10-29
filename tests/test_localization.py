from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from league_telegram_bot.handlers.core import BaseHandlers


@pytest.mark.parametrize(
    ("player", "expected_language"),
    [
        (SimpleNamespace(language="en"), "en"),
        (SimpleNamespace(language="ru"), "ru"),
        (SimpleNamespace(language="fr"), "ru"),
        (None, "ru"),
    ],
)
def test_language_for_user_uses_saved_language_or_russian_fallback(
    player: SimpleNamespace | None, expected_language: str
) -> None:
    handlers = object.__new__(BaseHandlers)
    handlers.players = Mock()
    handlers.players.get_player.return_value = player

    assert handlers.language_for_user(123) == expected_language


def test_language_for_user_without_user_id_falls_back_to_russian() -> None:
    handlers = object.__new__(BaseHandlers)
    handlers.players = Mock()

    assert handlers.language_for_user(None) == "ru"
    handlers.players.get_player.assert_not_called()


def test_translation_for_user_uses_saved_language_and_formats_arguments() -> None:
    handlers = object.__new__(BaseHandlers)
    handlers.players = Mock()
    handlers.players.get_player.return_value = SimpleNamespace(language="en")
    handlers.locales = {
        "welcome": {
            "ru": "Добро пожаловать, {name}!",
            "en": "Welcome, {name}!",
        }
    }

    assert handlers.tr_for_user(123, "welcome", name="Alex") == "Welcome, Alex!"
