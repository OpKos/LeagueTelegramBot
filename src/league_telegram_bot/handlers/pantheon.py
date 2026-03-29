from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..models import Event
from .decorators import command_handler

logger = logging.getLogger()


class PantheonHandlers:
    @command_handler("log")
    async def log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert update.effective_message
        assert user

        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /log <ссылка>")
            return

        link = context.args[0].strip()
        if not link:
            await update.effective_message.reply_text("Ссылка не должна быть пустой.")
            return

        player = self.players.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы.")
            return
        event = _resolve_event(self, player, update.effective_message.chat_id)
        if event is None:
            await update.effective_message.reply_text(
                "Не удалось определить событие. Используйте команду в чате стола."
            )
            return

        api_url = os.getenv("PANTHEON_API_URL", "https://gameapi.riichimahjong.org")

        client = PantheonClient(
            api_url,
            event_id=event.pantheon_id,
            server_path_prefix="/v2",
        )
        result = client.send_game_log(link)
        logger.info(str(result))
        if result.get("ok"):
            game = result.get("game", {})
            session_hash = game.get("session_hash", "—")
            await update.effective_message.reply_text(
                "Лог отправлен в Пантеон.\n"
                f"Сессия: {session_hash}\n"
                f"Игроков: {len(result.get('players', []))}"
            )
            logger.info(
                "Pantheon log sent by %s (%s) for event %s", user.username, user.id, event.id
            )
            return

        error = result.get("meta", "неизвестная ошибка").get("cause", "неизвестная ошибка")
        await update.effective_message.reply_text(f"Не удалось отправить лог: {error}")
        logger.warning("Pantheon log failed for %s (%s): %s", user.username, user.id, error)


def _resolve_event(handlers, player, chat_id: int | None) -> Event | None:
    if chat_id:
        table = handlers.tables.get_table(chat_id=chat_id)
        if table:
            return table.event
    return None


def _is_player_in_event(player, event_id: int) -> bool:
    return any(ep.event_id == event_id for ep in player.player_events)


def _maybe_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
