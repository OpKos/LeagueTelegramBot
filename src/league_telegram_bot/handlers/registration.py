from __future__ import annotations

import logging

import pytz
from telegram import Update
from telegram.ext import ContextTypes

from ..time_utils import now_in_timezone
from .decorators import command_handler
from .utils import log_command_event

logger = logging.getLogger(__name__)


class RegistrationHandlers:
    @command_handler("set_nickname")
    async def set_nickname_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Регистрирует нового игрока в системе."""
        user = update.effective_user
        args = context.args
        if update.effective_message.chat.type != "private":
            log_command_event(
                update, "set_nickname", "rejected", logger=logger, reason="not_private_chat"
            )
            await update.effective_message.reply_text(
                self.tr_for_user(user.id, "register_not_private_chat")
            )
            return
        if not args or len(args) != 1:
            log_command_event(
                update, "set_nickname", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(
                self.tr_for_user(user.id, "register_invalid_args")
            )
            return

        tenhou_name = args[0]

        player = self.players.get_player(telegram_id=user.id)
        if player:
            lang = player.language
            old_name = player.tenhou_name
            if old_name == tenhou_name:
                await update.effective_message.reply_text(
                    self.tr(lang, "already_registered", old=old_name, new=tenhou_name)
                )
            else:
                self.players.update_tenhou_nick(p_id=player.p_id, tenhou_name=tenhou_name)
                self.players.update_telegram_name(p_id=player.p_id, telegram_name=user.username)
                await update.effective_message.reply_text(
                    self.tr(lang, "nick_change", old=old_name, new=tenhou_name)
                )
            log_command_event(
                update,
                "set_nickname",
                "succeeded",
                logger=logger,
                action="nickname_unchanged" if old_name == tenhou_name else "nickname_updated",
            )
            return

        self.players.register_player(
            telegram_id=user.id, telegram_name=user.username, tenhou_id=tenhou_name
        )
        await update.effective_message.reply_text(
            self.tr("ru", "register_welcome")
            + "\n"
            + self.tr("en", "register_welcome")
            + "\nUse /set_language to change your language"
        )
        log_command_event(
            update, "set_nickname", "succeeded", logger=logger, action="player_registered"
        )

    @command_handler("set_language")
    async def set_language(self, update, context) -> None:
        user = update.effective_user
        user_id = user.id
        if not context.args or context.args[0] not in ("ru", "en"):
            log_command_event(
                update, "set_language", "rejected", logger=logger, reason="invalid_language"
            )
            await update.message.reply_text(self.tr_for_user(user.id, "language_invalid_args"))
            return

        lang = context.args[0]
        player = self.players.get_player(telegram_id=user_id)

        if not player:
            log_command_event(
                update, "set_language", "rejected", logger=logger, reason="not_registered"
            )
            await update.message.reply_text(self.tr(lang, "not_registered"))
            return

        self.players.set_language(player.p_id, lang)
        await update.message.reply_text(self.tr(lang, "language_set"))
        log_command_event(update, "set_language", "succeeded", logger=logger, language=lang)

    @command_handler("set_timezone")
    async def set_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message
        lang = self.language_for_user(user.id)
        if len(context.args) != 1 or context.args[0] not in pytz.all_timezones:
            log_command_event(
                update, "set_timezone", "rejected", logger=logger, reason="invalid_timezone"
            )
            await update.effective_message.reply_text(self.tr(lang, "timezone_invalid_args"))
            return

        player = self.players.get_player(telegram_id=user.id)
        if not player:
            log_command_event(
                update, "set_timezone", "rejected", logger=logger, reason="not_registered"
            )
            await update.effective_message.reply_text(self.tr(lang, "not_registered"))
            return

        timezone = context.args[0]
        if not self.players.set_timezone(player.p_id, timezone):
            log_command_event(
                update, "set_timezone", "failed", logger=logger, reason="player_not_found"
            )
            await update.effective_message.reply_text(self.tr(lang, "not_registered"))
            return
        current_time = now_in_timezone(timezone).strftime("%Y-%m-%d %H:%M")
        await update.effective_message.reply_text(
            self.tr(lang, "timezone_set", timezone=timezone, time=current_time)
        )
        log_command_event(update, "set_timezone", "succeeded", logger=logger, timezone=timezone)
