"""
Application wiring: build the PTB Application, register every handler, run the
post_init bootstrap (DB init + migrations, command list, bot description, request
queue) and start long-polling.

structure.py (repo root) only inserts bot/ on sys.path and calls main().
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
import time

from telegram import Update, BotCommand
from telegram.ext import (
    Application, ContextTypes,
    ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_LANG
from constants import (
    T_PREVIEW_EDIT, SET_BOT_DESCRIPTION, SET_BOT_SHORT_DESCRIPTION,
)
from db.storage import init_db, get_user, set_admin, get_setting
from db.migrate import run_migrations
from core.monitor import handle_channel_post
from core.queue import queue
from core.preview import (
    on_preview_ok, on_preview_no, on_preview_edit, on_preview_edit_text,
    on_preview_edit_cancel,
)
from handlers.start import get_start_handler
from handlers.menu import get_menu_handlers
from handlers.agent import get_agent_handlers
from handlers.help import get_help_handlers
from handlers.settings import get_settings_handlers
from handlers.stats import get_stats_handlers
from handlers.admin import get_admin_handlers
from texts import t

log = logging.getLogger(__name__)

PID_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tg_bot.pid")


# ───── single-instance guard (avoid 409 polling conflicts) ─────
def _kill_old_instance() -> None:
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        if old_pid == os.getpid():
            return
        log.info("Stopping old instance (PID %s)…", old_pid)
        os.kill(old_pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.2)
            try:
                os.kill(old_pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(old_pid, signal.SIGKILL)
    except (ValueError, OSError):
        pass
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _write_pid() -> None:
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid() -> None:
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


# ───── preview ✏️ edit conversation ─────
async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


def _preview_handlers() -> list:
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_preview_edit, pattern=r"^preview:edit:")],
        states={T_PREVIEW_EDIT: [
            CallbackQueryHandler(on_preview_edit_cancel, pattern=r"^preview:edit_cancel:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_preview_edit_text),
        ]},
        fallbacks=[
            CommandHandler("cancel", _cancel),
            CallbackQueryHandler(on_preview_edit_cancel, pattern=r"^preview:edit_cancel:"),
        ],
        per_message=False,
        name="preview_edit",
        persistent=False,
    )
    return [
        edit_conv,
        CallbackQueryHandler(on_preview_ok, pattern=r"^preview:ok:"),
        CallbackQueryHandler(on_preview_no, pattern=r"^preview:no:"),
    ]


# ───── lifecycle ─────
async def post_init(app: Application) -> None:
    await init_db()
    await run_migrations()
    log.info("Database ready (init + migrations).")

    # Flag known admins that already have a row; others pass via ADMIN_IDS anyway.
    for aid in ADMIN_IDS:
        try:
            if await get_user(aid):
                await set_admin(aid, True)
        except Exception as e:  # noqa: BLE001
            log.warning("admin seed failed for %s: %s", aid, e)

    await app.bot.set_my_commands([
        BotCommand("start", "Запуск / настройка"),
        BotCommand("menu", "Главное меню"),
        BotCommand("help", "Справка"),
        BotCommand("cancel", "Отмена"),
    ])

    long_desc = await get_setting(SET_BOT_DESCRIPTION) or t(DEFAULT_LANG, "bot_desc_long")
    short_desc = await get_setting(SET_BOT_SHORT_DESCRIPTION) or t(DEFAULT_LANG, "bot_desc_short")
    try:
        await app.bot.set_my_description(description=long_desc[:512])
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_description failed: %s", e)
    try:
        await app.bot.set_my_short_description(short_description=short_desc[:120])
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_short_description failed: %s", e)

    queue.start()
    log.info("Request queue started.")


async def post_shutdown(app: Application) -> None:
    await queue.stop()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled exception while processing update.", exc_info=context.error)


def build() -> Application:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # group 0 — commands, menus, conversations, callback routers.
    # Agent handlers are registered before the menu handlers so that pressing
    # Home mid-wizard exits the conversation cleanly (via its menu:home fallback)
    # instead of being swallowed by the standalone on_home handler.
    app.add_handler(get_start_handler(), group=0)
    for h in get_agent_handlers():
        app.add_handler(h, group=0)
    for h in get_menu_handlers():
        app.add_handler(h, group=0)
    for h in get_help_handlers():
        app.add_handler(h, group=0)
    for h in get_settings_handlers():
        app.add_handler(h, group=0)
    for h in get_stats_handlers():
        app.add_handler(h, group=0)
    for h in get_admin_handlers():
        app.add_handler(h, group=0)
    for h in _preview_handlers():
        app.add_handler(h, group=0)

    # group 1 — incoming channel posts (the actual rewriting pipeline)
    app.add_handler(
        MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post),
        group=1,
    )

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", encoding="utf-8")],
    )

    _kill_old_instance()
    _write_pid()
    atexit.register(_cleanup_pid)

    app = build()
    log.info("Bot starting (long-polling)…")
    app.run_polling(
        allowed_updates=[
            Update.MESSAGE, Update.CALLBACK_QUERY, Update.CHANNEL_POST,
            Update.MY_CHAT_MEMBER,
        ],
    )


if __name__ == "__main__":
    main()
