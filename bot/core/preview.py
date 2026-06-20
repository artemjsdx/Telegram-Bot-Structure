"""
Preview mode: send the proposed AI rewrite to the channel owner's DM with
✅ publish / ✏️ edit / ❌ reject controls before it touches the channel post.

Pending previews live in application.bot_data["pending_previews"], keyed by
"channel_id:message_id". Each entry keeps the original Message so the post can be
replaced on approval.
"""
from __future__ import annotations

import html
import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from constants import T_PREVIEW_EDIT
from core.replacer import replace_post
from keyboards.factory import preview_kb, preview_edit_kb
from texts import t

log = logging.getLogger(__name__)

PENDING_KEY = "pending_previews"


def _store(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.application.bot_data.setdefault(PENDING_KEY, {})


def _key(channel_id: int, msg_id: int) -> str:
    return f"{channel_id}:{msg_id}"


def _parse(data: str) -> tuple[str, int, int]:
    """`preview:<action>:<channel_id>:<msg_id>` → (action, channel_id, msg_id)."""
    parts = data.split(":")
    return parts[1], int(parts[2]), int(parts[3])


async def send_preview(
    context: ContextTypes.DEFAULT_TYPE,
    user: dict,
    message: Message,
    ai_text: str,
) -> None:
    """DM the proposed rewrite to the channel owner for confirmation."""
    lang = user.get("lang") or "ru"
    channel_id, msg_id = message.chat_id, message.message_id
    _store(context)[_key(channel_id, msg_id)] = {
        "message": message,
        "text": ai_text,
        "lang": lang,
        "user_id": user["user_id"],
    }
    body = t(lang, "preview_caption", chan=channel_id, text=ai_text)
    await context.bot.send_message(
        chat_id=user["user_id"],
        text=body,
        parse_mode=ParseMode.HTML,
        reply_markup=preview_kb(channel_id, msg_id, lang),
    )


async def on_preview_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, channel_id, msg_id = _parse(q.data)
    entry = _store(context).pop(_key(channel_id, msg_id), None)
    lang = (entry or {}).get("lang", "ru")
    if not entry:
        await q.edit_message_text(t(lang, "error_generic"))
        return
    try:
        await replace_post(context.bot, entry["message"], entry["text"])
        await q.edit_message_text(t(lang, "preview_published"))
    except Exception as e:
        log.error("Preview apply failed for %s: %s", _key(channel_id, msg_id), e)
        await q.edit_message_text(t(lang, "error_generic"))


async def on_preview_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, channel_id, msg_id = _parse(q.data)
    entry = _store(context).pop(_key(channel_id, msg_id), None)
    lang = (entry or {}).get("lang", "ru")
    await q.edit_message_text(t(lang, "preview_rejected"))


async def on_preview_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point of the edit conversation: show the current AI text as a
    tap-to-copy <code> "макет" the user can copy, tweak and resend, plus a
    Cancel button so they can back out without losing the original suggestion.
    """
    q = update.callback_query
    await q.answer()
    _, channel_id, msg_id = _parse(q.data)
    entry = _store(context).get(_key(channel_id, msg_id))
    lang = (entry or {}).get("lang", "ru")
    if not entry:
        await q.edit_message_text(t(lang, "error_generic"))
        return ConversationHandler.END
    context.user_data["preview_edit"] = (channel_id, msg_id)
    await q.edit_message_text(
        t(lang, "preview_edit_prompt", text=html.escape(entry.get("text", ""))),
        parse_mode=ParseMode.HTML,
        reply_markup=preview_edit_kb(channel_id, msg_id, lang),
    )
    return T_PREVIEW_EDIT


async def on_preview_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel button while waiting for corrected text: restore the preview unchanged."""
    q = update.callback_query
    await q.answer()
    _, channel_id, msg_id = _parse(q.data)
    context.user_data.pop("preview_edit", None)
    entry = _store(context).get(_key(channel_id, msg_id))
    lang = (entry or {}).get("lang", "ru")
    if not entry:
        await q.edit_message_text(t(lang, "error_generic"))
        return ConversationHandler.END
    await q.edit_message_text(
        t(lang, "preview_caption", chan=channel_id, text=entry.get("text", "")),
        parse_mode=ParseMode.HTML,
        reply_markup=preview_kb(channel_id, msg_id, lang),
    )
    return ConversationHandler.END


async def on_preview_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the corrected text, update the pending entry, re-show preview."""
    pair = context.user_data.pop("preview_edit", None)
    entry = _store(context).get(_key(*pair)) if pair else None
    if not entry:
        await update.message.reply_text(t("ru", "error_generic"))
        return ConversationHandler.END
    new_text = update.message.text or update.message.caption or ""
    lang = entry.get("lang", "ru")
    entry["text"] = new_text
    channel_id, msg_id = pair
    await update.message.reply_text(
        t(lang, "preview_caption", chan=channel_id, text=new_text),
        parse_mode=ParseMode.HTML,
        reply_markup=preview_kb(channel_id, msg_id, lang),
    )
    return ConversationHandler.END
