"""Help screen: /help command and the menu:help button."""
from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import OWNER_ID
from db.storage import get_user
from handlers.menu import nav
from keyboards.factory import home_btn
from texts import t

log = logging.getLogger(__name__)


async def _support_handle(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Owner's current @username, resolved live from OWNER_ID.

    Falls back to a tap-to-open mention link if the handle can't be fetched or
    the owner has no public username.
    """
    try:
        chat = await context.bot.get_chat(OWNER_ID)
        if chat.username:
            return f"@{chat.username}"
        name = chat.full_name or "поддержка"
        return f'<a href="tg://user?id={OWNER_ID}">{name}</a>'
    except Exception as e:  # noqa: BLE001
        log.warning("Could not resolve owner handle for %s: %s", OWNER_ID, e)
        return f'<a href="tg://user?id={OWNER_ID}">поддержка</a>'


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
