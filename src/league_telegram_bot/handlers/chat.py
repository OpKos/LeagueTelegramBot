from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .decorators import callback_query_handler, command_handler

logger = logging.getLogger()


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
            await update.effective_message.reply_text(
                "Доступно только в супергруппах. (В настройках группы включите историю чата для новых участников)"
            )
            return
        member = await update.effective_message.chat.get_member(context.bot.id)
        if member.status != "administrator":
            await update.effective_message.reply_text(
                "Сначала назначьте боту права администратора."
            )
            return
        user = update.effective_user
        logger.info(
            "Пользователь %s (%s) вызвал /set_chat в чате %s",
            user.username,
            user.id,
            update.effective_message.chat.id,
        )
        t = self.tables.get_table(chat_id=update.effective_message.chat.id)
        if t:
            await update.effective_message.reply_text(f"У этого чата уже есть стол {t.name}.")
            return
        player = self.players.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы.")
            return
        table_names = [table.name for table in player.visible_tables() if table.chat_id == 0]
        if not table_names:
            await update.effective_message.reply_text("У вас нет нераскрытых столов.")
            return
        keyboard = [
            [InlineKeyboardButton(t_n, callback_data="TC" + t_n)] for t_n in table_names
        ] + [[InlineKeyboardButton("Отмена", callback_data="TCCancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите стол", reply_markup=reply_markup)
