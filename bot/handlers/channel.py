"""
Channels section: list linked channels, link a new one (via a forwarded post),
pick the active channel, and unlink with confirmation.
"""
from __future__ import annotations

import logging

from telegram import (
    Update, MessageOriginChannel,
    ChatMemberAdministrator, ChatMemberOwner,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from constants import T_ADD_CHANNEL
from db.storage import (
    get_user, upsert_user, get_channels_for_user, add_channel, remove_channel,
)
from handlers.menu import nav
from keyboards.factory import channels_kb, channel_actions_kb, confirm_kb, home_btn
from texts import t

from telegram import InlineKeyboardMarkup

log = logging.getLogger(__name__)


def _find(channels: list[dict], cid: int) -> dict | None:
    for ch in channels:
        if ch["channel_id"] == cid:
            return ch
    return None


async def verify_forwarded_channel(msg, bot) -> tuple[int, str] | None:
    """
    Validate that `msg` is a post forwarded from a channel where the bot is an
    admin/owner. Returns (channel_id, title) on success, or None otherwise.
    Shared by the channels section and the agent wizard's bind step.
    """
    fwd = getattr(msg, "forward_origin", None)
    if not fwd or not isinstance(fwd, MessageOriginChannel):
        return None
    cid = fwd.chat.id
    title = fwd.chat.title or fwd.chat.username or str(cid)
    try:
        member = await bot.get_chat_member(cid, bot.id)
    except Exception:
        return None
    if not isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
        return None
    return cid, title


async def _render_list(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    channels = [c for c in await get_channels_for_user(update.effective_user.id) if c.get("active", 1)]
    active_id = (user or {}).get("active_channel_id")
    text = t(lang, "channels_title") if channels else t(lang, "channels_empty")
    kb = channels_kb(channels, active_id, lang)
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _render_list(update, context, edit=False)


async def on_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    ch = _find(await get_channels_for_user(q.from_user.id), cid)
    if not ch:
        await _render_list(update, context, edit=True)
        return
    title = ch.get("chan_title") or str(cid)
    is_active = (user or {}).get("active_channel_id") == cid
    text = f"{t(lang, 'channels_title')}\n\n📣 <b>{title}</b>\n<code>{cid}</code>"
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=channel_actions_kb(cid, is_active, lang),
    )


async def on_set_active(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    cid = int(q.data.split(":")[2])
    await upsert_user(q.from_user.id, active_channel_id=cid)
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.answer(t(lang, "channel_active_set"))
    context.args = None
    # re-render the channel view
    q.data = f"chan:view:{cid}"
    await on_view(update, context)


async def on_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    ch = _find(await get_channels_for_user(q.from_user.id), cid)
    title = (ch or {}).get("chan_title") or str(cid)
    await q.edit_message_text(
        t(lang, "channel_confirm_remove", title=title),
        reply_markup=confirm_kb(f"chan:remove_yes:{cid}", f"chan:view:{cid}", lang),
    )


async def on_remove_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    cid = int(q.data.split(":")[2])
    await remove_channel(q.from_user.id, cid)
    user = await get_user(q.from_user.id)
    if (user or {}).get("active_channel_id") == cid:
        await upsert_user(q.from_user.id, active_channel_id=None)
    lang = (user or {}).get("lang") or "ru"
    await q.answer(t(lang, "channel_removed"))
    await _render_list(update, context, edit=True)


# ───── Add channel (forwarded post) ─────
async def ask_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(t(lang, "channel_add_howto"), parse_mode=ParseMode.HTML)
    return T_ADD_CHANNEL


async def got_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    user = await get_user(msg.from_user.id)
    lang = (user or {}).get("lang") or "ru"

    result = await verify_forwarded_channel(msg, context.bot)
    if result is None:
        await msg.reply_text(t(lang, "channel_not_forwarded"))
        return T_ADD_CHANNEL
    cid, title = result

    provider = (user or {}).get("provider") or "favoriteapi"
    await add_channel(msg.from_user.id, cid, chan_title=title, provider=provider)
    if not (user or {}).get("active_channel_id"):
        await upsert_user(msg.from_user.id, active_channel_id=cid)

    kb = InlineKeyboardMarkup([[home_btn(lang)]])
    await msg.reply_html(t(lang, "channel_added", title=title), reply_markup=kb)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


def get_channel_handlers() -> list:
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_add, pattern=r"^chan:add$")],
        states={T_ADD_CHANNEL: [MessageHandler(filters.FORWARDED & ~filters.COMMAND, got_forward)]},
        fallbacks=[CallbackQueryHandler(cancel, pattern=r"^menu:")],
        per_message=False,
        name="channel_add",
        persistent=False,
    )
    return [
        add_conv,
        CallbackQueryHandler(show_channels, pattern=r"^menu:channels$"),
        CallbackQueryHandler(on_view, pattern=r"^chan:view:"),
        CallbackQueryHandler(on_set_active, pattern=r"^chan:active:"),
        CallbackQueryHandler(on_remove_yes, pattern=r"^chan:remove_yes:"),
        CallbackQueryHandler(on_remove, pattern=r"^chan:remove:"),
    ]
