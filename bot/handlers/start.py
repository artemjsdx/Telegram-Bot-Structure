"""
/start entry point.

Banned users are turned away. Configured users land on the main menu; new users
get a welcome with a button that launches the onboarding conversation
(`setup:begin`, owned by handlers/setup.py).
"""
from __future__ import annotations

import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from config import ADMIN_IDS, DEFAULT_LANG
from db.storage import get_user, upsert_user
from handlers.menu import send_main_menu
from texts import t


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if user is None:
        await upsert_user(
            user_id,
            lang=DEFAULT_LANG,
            created_at=int(time.time()),
            is_admin=1 if user_id in ADMIN_IDS else 0,
        )
        user = await get_user(user_id)

    lang = user.get("lang") or DEFAULT_LANG

    if user.get("is_banned"):
        await update.message.reply_text(t(lang, "banned_msg"))
        return

    if user.get("setup_done"):
        await send_main_menu(update, context)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "agent_create"), callback_data="agent:new")],
        [InlineKeyboardButton(t(lang, "agent_skip_setup"), callback_data="agent:skip_setup")],
    ])
    await update.message.reply_text(
        t(lang, "start_welcome"), parse_mode=ParseMode.HTML, reply_markup=kb
    )


def get_start_handler() -> CommandHandler:
    return CommandHandler("start", cmd_start)
