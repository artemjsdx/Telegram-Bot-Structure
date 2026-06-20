"""
Main-menu navigation.

send_main_menu() renders the home screen, optionally with an admin-configured
photo/video banner above the buttons. Because Telegram cannot edit a text message
into a media message (or vice versa), navigation deletes the current message and
sends a fresh one — uniform and safe for both text submenus and the media home.
"""
from __future__ import annotations

import io
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import ADMIN_IDS
from constants import (
    SET_BANNER_TYPE, SET_BANNER_FILE_ID, BANNER_PHOTO, BANNER_VIDEO,
    SET_MENU_CHANNEL_ENABLED, SET_MENU_CHANNEL_LINK,
)
from db.storage import get_user, get_setting, get_agents_for_user, touch_user
from keyboards.factory import agents_list_kb
from texts import t

log = logging.getLogger(__name__)


def is_admin(user: dict | None, user_id: int) -> bool:
    return user_id in ADMIN_IDS or bool(user and user.get("is_admin"))


async def _menu_channel_line(lang: str) -> str:
    """Optional bot-channel line for the main menu (empty when disabled/unset).

    Returned as an HTML anchor so Telegram shows no link-preview banner.
    """
    if (await get_setting(SET_MENU_CHANNEL_ENABLED)) != "1":
        return ""
    link = await get_setting(SET_MENU_CHANNEL_LINK)
    if not link:
        return ""
    return "\n\n" + t(lang, "menu_channel_line", link=link)


async def _delete_origin(update: Update) -> None:
    q = update.callback_query
    if q:
        try:
            await q.message.delete()
        except Exception:
            pass


async def nav(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None) -> None:
    """Show a text screen: delete the message we came from, send a fresh one."""
    if update.callback_query:
        await update.callback_query.answer()
    await _delete_origin(update)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def nav_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo_bytes: bytes | None,
    caption: str,
    reply_markup=None,
) -> None:
    """Show a photo screen with buttons: delete the origin, send a fresh photo.

    Used by stats screens that attach a chart. Since Telegram can't edit a text
    message into a media one (or back), we always delete + resend, so the inline
    buttons keep working whether we came from text or from another photo. If
    photo_bytes is None (no data to chart), falls back to a plain text screen.
    """
    if photo_bytes is None:
        await nav(update, context, caption, reply_markup)
        return
    if update.callback_query:
        await update.callback_query.answer()
    await _delete_origin(update)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=io.BytesIO(photo_bytes),
        caption=caption[:1024],
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = (user or {}).get("lang") or "ru"

    # Refresh @username/display name for the admin user list on every visit.
    eu = update.effective_user
    await touch_user(user_id, eu.username or "", eu.first_name or "")

    agents = await get_agents_for_user(user_id)
    kb = agents_list_kb(agents, lang, is_admin(user, user_id))
    text = (t(lang, "agents_title") if agents else t(lang, "agents_empty"))
    text += await _menu_channel_line(lang)

    if update.callback_query:
        await update.callback_query.answer()
        await _delete_origin(update)

    chat_id = update.effective_chat.id
    banner_type = await get_setting(SET_BANNER_TYPE)
    banner_id = await get_setting(SET_BANNER_FILE_ID)

    if banner_id and banner_type in (BANNER_PHOTO, BANNER_VIDEO):
        try:
            send = context.bot.send_photo if banner_type == BANNER_PHOTO else context.bot.send_video
            kwarg = "photo" if banner_type == BANNER_PHOTO else "video"
            await send(chat_id, **{kwarg: banner_id}, caption=text,
                       parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception as e:
            log.warning("Banner send failed (%s) — falling back to text menu.", e)

    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb,
        disable_web_page_preview=True,
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update, context)


async def on_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update, context)


def get_menu_handlers() -> list:
    return [
        CommandHandler("menu", cmd_menu),
        CallbackQueryHandler(on_home, pattern=r"^menu:home$"),
    ]
