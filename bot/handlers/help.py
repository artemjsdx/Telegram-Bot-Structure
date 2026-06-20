"""Help screen: /help command and the menu:help button."""
from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import OWNER_ID
from constants import SET_SUPPORT_ID
from db.storage import get_user, get_setting
from handlers.menu import nav
from keyboards.factory import home_btn
from texts import t

log = logging.getLogger(__name__)


async def _support_handle(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Support contact's current @username, resolved live.

    Uses the admin-configured support ID if set, otherwise OWNER_ID. Falls back
    to a tap-to-open mention link if the handle can't be fetched or the contact
    has no public username.
    """
    sid = await get_setting(SET_SUPPORT_ID)
    try:
        support_id = int(sid) if sid else OWNER_ID
    except (TypeError, ValueError):
        support_id = OWNER_ID
    try:
        chat = await context.bot.get_chat(support_id)
        if chat.username:
            return f"@{chat.username}"
        name = chat.full_name or "поддержка"
        return f'<a href="tg://user?id={support_id}">{name}</a>'
    except Exception as e:  # noqa: BLE001
        log.warning("Could not resolve support handle for %s: %s", support_id, e)
        return f'<a href="tg://user?id={support_id}">поддержка</a>'


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    kb = InlineKeyboardMarkup([[home_btn(lang)]])
    text = t(lang, "help_text", support=await _support_handle(context))
    if update.callback_query:
        await nav(update, context, text, kb)
    else:
        await update.message.reply_html(text, reply_markup=kb)


def get_help_handlers() -> list:
    return [
        CommandHandler("help", show_help),
        CallbackQueryHandler(show_help, pattern=r"^menu:help$"),
    ]
