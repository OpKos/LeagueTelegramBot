from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .decorators import command_handler

logger = logging.getLogger()


class RegistrationHandlers:
    @command_handler("register")
    async def register_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Регистрирует нового игрока в системе.

        Args:
            update (Update): Объект Update от Telegram.
            context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
        """
        user = update.effective_user
        args = context.args
        assert update.effective_message
        assert user
        logger.info(
            "User %s (%s) issued /register command with args: %s", user.username, user.id, args
        )

        if not args or len(args) != 1:
            logger.info(
                "User %s (%s) used /register with invalid args: %s", user.username, user.id, args
            )
            await update.effective_message.reply_text(self.tr("en", "register_invalid_args"))
            return

        tenhou_name = args[0]

        player = self.db.get_player(telegram_id=user.id)
        if player:
            lang = player.language
            old_name = player.tenhou_name
            if old_name == tenhou_name:
                await update.effective_message.reply_text(
                    self.tr(lang, "already_registered", old=old_name, new=tenhou_name)
                )
            else:
                self.db.update_tenhou_nick(p_id=player.p_id, tenhou_name=tenhou_name)
                await update.effective_message.reply_text(
                    self.tr(lang, "nick_change", old=old_name, new=tenhou_name)
                )
            logger.info(
                "User %s (%s) already registered with Tenhou ID %s.",
                user.username,
                user.id,
                tenhou_name,
            )
            return

        self.db.register_player(
            telegram_id=user.id, telegram_name=user.username, tenhou_id=tenhou_name
        )
        await update.effective_message.reply_text(
            self.tr("ru", "register_success")
            + "\n"
            + self.tr("en", "register_success")
            + "\nUse /set_language to change your language"
        )
        logger.info(
            "User %s (%s) registered with Tenhou ID %s.", user.username, user.id, tenhou_name
        )

    @command_handler("set_language")
    async def set_language(self, update, context) -> None:
        user_id = update.effective_user.id
        if not context.args or context.args[0] not in ("ru", "en"):
            await update.message.reply_text("Usage: /set_language ru|en")
            return

        lang = context.args[0]
        p_id = self.db.get_player(telegram_id=user_id).p_id

        if not p_id:
            await update.message.reply_text(self.tr(lang, "not_registered"))
            return

        self.db.set_language(p_id, lang)
        await update.message.reply_text(self.tr(lang, "language_set"))
