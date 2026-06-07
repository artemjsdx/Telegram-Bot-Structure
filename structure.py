import logging
import sys
import os
import signal
import atexit

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

        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

PID_FILE = "/data/data/com.termux/files/home/tg_bot.pid"


def kill_old_instance():
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        if old_pid == os.getpid():
            return
        logger.info(f"Stopping old instance (PID {old_pid})...")
        os.kill(old_pid, signal.SIGTERM)
        import time
        for _ in range(30):
            time.sleep(0.2)
            try:
                os.kill(old_pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(old_pid, signal.SIGKILL)
        logger.info("Old instance stopped.")
    except (ValueError, OSError):
        pass
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


async def status_command(update, context):
    from db.storage import get_user
    user = await get_user(update.effective_user.id)
    if not user or not user.get("setup_done"):
        await update.message.reply_text("Бот не настроен. /start")
        return
    chan = user.get("chan_title") or "не привязан"
    monitoring = "активен" if user.get("channel_id") else "не привязан"
    sys_on = "ВКЛ" if user.get("sys_prompt", 1) else "ВЫКЛ"
    model = user.get("model_id", "—")
    await update.message.reply_html(
        f"<b>Статус</b>\n\n"
        f"Канал: {chan} — {monitoring}\n"
        f"Модель: <code>{model}</code>\n"
        f"Системный промпт: {sys_on}"
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

    kill_old_instance()
    write_pid()
    atexit.register(cleanup_pid)

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
