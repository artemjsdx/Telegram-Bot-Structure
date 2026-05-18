import logging
from telegram import Update, MessageOriginChannel
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram import ChatMemberAdministrator, ChatMemberOwner

from db.storage import get_user, upsert_user

logger = logging.getLogger(__name__)

WAIT_FORWARD = 10


async def bind_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user or not user.get("setup_done"):
        await update.message.reply_text("❌ Сначала пройди настройку: /start")
        return ConversationHandler.END

    await update.message.reply_html(
        "📣 <b>Привязка канала</b>\n\n"
        "1. Добавь бота в канал как <b>администратора</b>\n"
        "   Нужные права:\n"
        "   • Публикация сообщений\n"
        "   • Редактирование сообщений\n"
        "   • Удаление сообщений\n\n"
        "2. Перешли мне <b>любой пост</b> из этого канала 👇\n\n"
        "/cancel — отмена"
    )
    return WAIT_FORWARD


async def got_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    fwd = msg.forward_origin
    if not fwd:
        await msg.reply_text(
            "❌ Это не пересланный пост.\nПерешли сообщение из своего канала."
        )
        return WAIT_FORWARD

    if not isinstance(fwd, MessageOriginChannel):
        await msg.reply_text(
            "❌ Перешли пост именно из канала (не из группы/личных сообщений)."
        )
        return WAIT_FORWARD

    channel_id = fwd.chat.id
    chan_title = fwd.chat.title or fwd.chat.username or str(channel_id)

    checking = await msg.reply_text("⏳ Проверяю права бота в канале...")

    try:
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)

        if not isinstance(bot_member, (ChatMemberAdministrator, ChatMemberOwner)):
            await checking.edit_text(
                "❌ Бот не является администратором этого канала.\n\n"
                "Добавь бота как администратора и попробуй снова."
            )
            return WAIT_FORWARD

        await upsert_user(user_id, channel_id=channel_id, chan_title=chan_title)

        can_post = getattr(bot_member, "can_post_messages", False)
        can_edit = getattr(bot_member, "can_edit_messages", False)
        can_del = getattr(bot_member, "can_delete_messages", False)

        warnings = []
        if not can_post:
            warnings.append("⚠️ Нет права публикации — посты не будут отправляться")
        if not can_edit:
            warnings.append("⚠️ Нет права редактирования — будет использоваться удаление+отправка")
        if not can_del:
            warnings.append("⚠️ Нет права удаления — оригинальный пост останется")

        warn_text = ("\n\n" + "\n".join(warnings)) if warnings else ""

        await checking.edit_text(
            f"✅ <b>Канал привязан!</b>\n\n"
            f"📣 <b>{chan_title}</b>\n"
            f"ID: <code>{channel_id}</code>\n\n"
            f"Права: {'✅' if can_post else '❌'} пост  "
            f"{'✅' if can_edit else '❌'} ред.  "
            f"{'✅' if can_del else '❌'} удал.\n\n"
            f"🟢 <b>Мониторинг активен!</b> "
            f"Новые посты будут переписываться ИИ.{warn_text}",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    except Exception as e:
        await checking.edit_text(
            f"❌ Ошибка: <code>{e}</code>\n\n"
            "Убедись, что бот добавлен в канал как администратор.",
            parse_mode="HTML",
        )
        return WAIT_FORWARD


async def cancel_bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


def get_channel_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("bind_channel", bind_channel_start)],
        states={
            WAIT_FORWARD: [
                MessageHandler(filters.ALL & ~filters.COMMAND, got_forwarded)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_bind)],
        name="channel_conversation",
        persistent=False,
    )
