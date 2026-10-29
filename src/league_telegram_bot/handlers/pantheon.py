from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..leaderboard.logic import get_leaderboard_image
from ..models import Event
from .decorators import command_handler
from .utils import log_command_event

logger = logging.getLogger(__name__)


class PantheonHandlers:
    @command_handler("log")
    async def log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert update.effective_message
        assert user
        lang = self.language_for_user(user.id)

        if not context.args or len(context.args) != 1:
            log_command_event(update, "log", "rejected", logger=logger, reason="invalid_arguments")
            await update.effective_message.reply_text(self.tr(lang, "log_usage"))
            return

        link = context.args[0].strip()
        if not link:
            log_command_event(update, "log", "rejected", logger=logger, reason="empty_link")
            await update.effective_message.reply_text(self.tr(lang, "log_empty_link"))
            return

        event = _resolve_event(self, update.effective_message.chat_id)
        if event is None:
            log_command_event(update, "log", "rejected", logger=logger, reason="event_not_found")
            await update.effective_message.reply_text(self.tr(lang, "log_event_not_found"))
            return

        api_url = os.getenv("PANTHEON_GAME_API_URL", "https://gameapi.riichimahjong.org")

        client = PantheonClient(
            api_url,
            event_id=event.pantheon_id,
            server_path_prefix="/v2",
        )
        result = client.send_game_log(link)
        if result.get("ok"):
            game = result.get("game", {})
            session_hash = game.get("session_hash", "—")
            await update.effective_message.reply_text(
                self.tr(
                    lang,
                    "log_success",
                    link=f"https://rating.riichimahjong.org/event/{event.pantheon_id}/game/{session_hash}",
                )
            )
            log_command_event(update, "log", "succeeded", logger=logger, event_id=event.id)
            return

        error = result.get("meta", "неизвестная ошибка").get("cause", "неизвестная ошибка")
        await update.effective_message.reply_text(self.tr(lang, "log_failed", reason=error))
        log_command_event(update, "log", "failed", logger=logger, event_id=event.id, reason=error)

    @command_handler("fill_pantheon_ids")
    async def find_ids_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        lang = self.language_for_user(user.id)
        if not self.is_admin(user.id):
            log_command_event(
                update, "fill_pantheon_ids", "rejected", logger=logger, reason="admin_only"
            )
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
                output.append(
                    self.tr(
                        lang,
                        "pantheon_player_found",
                        player=player.tenhou_name,
                        player_id=pantheon_id,
                    )
                )
            else:
                output.append(self.tr(lang, "pantheon_player_not_found", player=player.tenhou_name))
        if len(output) == 0:
            log_command_event(
                update,
                "fill_pantheon_ids",
                "succeeded",
                logger=logger,
                updated_players=0,
            )
            await update.effective_message.reply_text(self.tr(lang, "pantheon_players_without_ids"))
            return
        await update.effective_message.reply_text("\n".join(output))
        log_command_event(
            update,
            "fill_pantheon_ids",
            "succeeded",
            logger=logger,
            updated_players=len(output),
        )

    @command_handler("leaderboard")
    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        lang = self.language_for_user(user.id)
        if not self.is_admin(user.id):
            log_command_event(update, "leaderboard", "rejected", logger=logger, reason="admin_only")
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
            image_link = get_leaderboard_image(
                event=event, pantheon_data=result.get("players"), timezone=self.timezone
            )
            await update.effective_message.chat.send_photo(photo=image_link)
            log_command_event(update, "leaderboard", "succeeded", logger=logger, event_id=event.id)
            return
        error = result.get("error", "неизвестная ошибка")
        await update.effective_message.reply_text(self.tr(lang, "leaderboard_failed", reason=error))
        log_command_event(
            update, "leaderboard", "failed", logger=logger, event_id=event.id, reason=error
        )


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
