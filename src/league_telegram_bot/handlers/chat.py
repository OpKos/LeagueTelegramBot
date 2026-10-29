from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .decorators import callback_query_handler, command_handler
from .utils import log_command_event

logger = logging.getLogger(__name__)


class ChatHandlers:
    @callback_query_handler(pattern=r"^TC")
    async def chat_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        chat = query.message.chat
        chat_id = chat.id
        data = query.data[2:]
        if data == "Cancel":
            await query.answer()
            await query.edit_message_text(text="Отменено")
        table_name = data
        table = self.tables.get_table(table_name=table_name)
        self.tables.set_table_chat(table.table_id, chat_id)
        await query.answer()
        await query.edit_message_text(text=f"Выбран стол {table_name}")
        try:
            await chat.set_title(f"Кава стол {table_name}")
        except Exception as e:
            logger.error(e)
        try:
            link = await context.bot.create_chat_invite_link(chat_id=chat_id)
        except Exception as e:
            await chat.send_message("Ошибка.")
            logger.error(e)
            return
        for player in table.players():
            member = await chat.get_member(player.telegram_id)
            logger.info(member)
            if str(member.status).lower() == "left":
                try:
                    await context.bot.send_message(
                        chat_id=player.telegram_id,
                        text=f"Чат стола {table_name}:\n{link.invite_link}",
                    )
                    await chat.send_message(f"Ссылка отправлена {player.irl_name}.")
                except Exception as e:
                    await chat.send_message(f"Не удалось пригласить игрока {player.irl_name}.")
                    logger.error(e)

    @command_handler("set_chat")
    async def set_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message.chat.type != "supergroup":
            log_command_event(
                update, "set_chat", "rejected", logger=logger, reason="supergroup_required"
            )
            await update.effective_message.reply_text(
                "Доступно только в супергруппах. (В настройках группы включите историю чата для новых участников)"
            )
            return
        count = await update.effective_message.chat.get_member_count()
        if count > 15:
            log_command_event(
                update,
                "set_chat",
                "rejected",
                logger=logger,
                reason="chat_too_large",
                member_count=count,
            )
            await update.effective_message.reply_text("Слишком большой чат.")
            return
        member = await update.effective_message.chat.get_member(context.bot.id)
        if member.status != "administrator":
            log_command_event(update, "set_chat", "rejected", logger=logger, reason="bot_not_admin")
            await update.effective_message.reply_text(
                "Сначала назначьте боту права администратора."
            )
            return
        user = update.effective_user
        t = self.tables.get_table(chat_id=update.effective_message.chat.id)
        if t:
            log_command_event(
                update, "set_chat", "rejected", logger=logger, reason="table_already_assigned"
            )
            await update.effective_message.reply_text(f"У этого чата уже есть стол {t.name}.")
            return
        player = self.players.get_player(telegram_id=user.id)
        if not player:
            log_command_event(
                update, "set_chat", "rejected", logger=logger, reason="not_registered"
            )
            await update.effective_message.reply_text("Вы не зарегистрированы.")
            return
        table_names = [table.name for table in player.all_tables() if table.chat_id == 0]
        if not table_names:
            log_command_event(
                update, "set_chat", "rejected", logger=logger, reason="no_available_tables"
            )
            await update.effective_message.reply_text("У вас нет нераскрытых столов.")
            return
        keyboard = [
            [InlineKeyboardButton(t_n, callback_data="TC" + t_n)] for t_n in table_names
        ] + [[InlineKeyboardButton("Отмена", callback_data="TCCancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите стол", reply_markup=reply_markup)
        log_command_event(
            update,
            "set_chat",
            "succeeded",
            logger=logger,
            available_tables=len(table_names),
        )
