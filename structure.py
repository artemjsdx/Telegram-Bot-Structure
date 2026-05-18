import logging
import sys
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Add bot/ subdir to sys.path so all module imports work
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot"))

from config import BOT_TOKEN
from db.storage import init_db
from handlers.setup import get_setup_handler
from handlers.channel import get_channel_handler
from handlers.settings import get_settings_handler
from core.monitor import handle_channel_post

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def status_command(update, context):
    from db.storage import get_user
    user = await get_user(update.effective_user.id)
    if not user or not user.get("setup_done"):
        await update.message.reply_text("❌ Бот не настроен. /start")
        return
    chan = user.get("chan_title") or "не привязан"
    monitoring = "🟢 активен" if user.get("channel_id") else "🔴 не привязан"
    await update.message.reply_html(
        f"📊 <b>Статус</b>\n\n"
        f"📣 Канал: {chan} — {monitoring}\n"
        f"🤖 Модель: <code>{user.get('model_id', '—')}</code>\n"
        f"🎨 Системный промпт: {'ВКЛ ✅' if user.get('sys_prompt', 1) else 'ВЫКЛ ❌'}"
    )


async def help_command(update, context):
    await update.message.reply_html(
        "<b>Команды:</b>\n\n"
        "/start — настройка бота\n"
        "/bind_channel — привязать Telegram-канал\n"
        "/settings — изменить настройки\n"
        "/status — статус мониторинга\n"
        "/cancel — отменить текущее действие\n"
        "/help — эта справка"
    )


async def post_init(app: Application):
    await init_db()
    logger.info("Database initialized")
    await app.bot.set_my_commands([
        ("start", "Настройка бота"),
        ("bind_channel", "Привязать канал"),
        ("settings", "Настройки"),
        ("status", "Статус мониторинга"),
        ("help", "Справка"),
        ("cancel", "Отменить"),
    ])
    logger.info("Commands set")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env!")
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(get_setup_handler(), group=0)
    app.add_handler(get_channel_handler(), group=0)
    app.add_handler(get_settings_handler(), group=0)

    app.add_handler(CommandHandler("status", status_command), group=1)
    app.add_handler(CommandHandler("help", help_command), group=1)

    app.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, handle_channel_post),
        group=2,
    )

    logger.info("Bot starting with polling...")
    app.run_polling(
        allowed_updates=[
            Update.MESSAGE,
            Update.CALLBACK_QUERY,
            Update.CHANNEL_POST,
            Update.EDITED_CHANNEL_POST,
        ]
    )


if __name__ == "__main__":
    main()
