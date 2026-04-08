from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..leaderboard.logic import make_leaderboard
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

        event = _resolve_event(self, update.effective_message.chat_id)
        if event is None:
            await update.effective_message.reply_text(
                "Не удалось определить событие. Используйте команду в чате стола."
            )
            return

        api_url = os.getenv("PANTHEON_GAME_API_URL", "https://gameapi.riichimahjong.org")

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
                f"Ссылка на игру: https://rating.riichimahjong.org/event/{event.pantheon_id}/game/{session_hash}"
            )
            logger.info(
                "Pantheon log sent by %s (%s) for event %s", user.username, user.id, event.id
            )
            return

        error = result.get("meta", "неизвестная ошибка").get("cause", "неизвестная ошибка")
        await update.effective_message.reply_text(f"Не удалось отправить лог: {error}")
        logger.warning("Pantheon log failed for %s (%s): %s", user.username, user.id, error)

    @command_handler("fill_pantheon_ids")
    async def find_ids_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.effective_message.reply_text("🔒 Admin only command")
            return

        api_url = os.getenv("PANTHEON_USER_API_URL", "https://userapi.riichimahjong.org")

        client = PantheonClient(
            api_url,
            server_path_prefix="/v2",
        )
        targets = self.players.get_unfilled_pantheon_players()
        output = []
        for player in targets:
            result = client.get_person_by_tenhou(player.tenhou_name)
            if result.get("people", ""):
                pantheon_id = result.get("people")[0].get("id")
                self.players.set_pantheon_id(player.p_id, pantheon_id)
                output.append(f"Player {player.tenhou_name} found: id {pantheon_id}")
            else:
                output.append(f"Player {player.tenhou_name} not found")
        if len(output) == 0:
            await update.effective_message.reply_text("Игроки без id не найдены")
            return
        await update.effective_message.reply_text("\n".join(output))

    @command_handler("leaderboard")
    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.effective_message.reply_text("🔒 Admin only command")
            return
        event_id = int(context.args[0])

        api_url = os.getenv("PANTHEON_USER_API_URL", "https://gameapi.riichimahjong.org")

        client = PantheonClient(
            api_url,
            server_path_prefix="/v2",
        )
        event = self.events.get_event(event_id)
        result = client.get_rating_table(
            event_id_list=[event.pantheon_id], order="desc", order_by="rating"
        )
        if result.get("ok"):
            image_link = make_leaderboard(event=event, pantheon_data=result.get("players"))
            await update.effective_message.chat.send_photo(photo=image_link)
            return
        error = result.get("error", "неизвестная ошибка")
        await update.effective_message.reply_text(f"Не удалось получить таблицу: {error}")
        logger.warning("Leaderboard failed for %s (%s): %s", user.username, user.id, error)


def _resolve_event(handlers, chat_id: int | None) -> Event | None:
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
