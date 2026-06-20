"""
Prompt section: view / edit the rewrite prompt, apply a preset, toggle the
formatting system-prompt.
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from constants import T_EDIT_PROMPT
from core.formatter import list_presets, get_preset
from db.storage import get_user, upsert_user
from handlers.menu import nav
from keyboards.factory import prompt_kb, presets_kb
from texts import t


async def _render(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    text = t(lang, "prompt_title")
    kb = prompt_kb(user or {}, lang)
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


async def show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _render(update, context, edit=False)


async def on_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    prompt = (user or {}).get("user_prompt") or ""
    body = t(lang, "prompt_current", prompt=prompt) if prompt else t(lang, "prompt_empty")
    await q.edit_message_text(body, parse_mode=ParseMode.HTML, reply_markup=prompt_kb(user or {}, lang))


async def on_toggle_sys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = await get_user(q.from_user.id)
    new_val = 0 if (user or {}).get("sys_prompt", 1) else 1
    await upsert_user(q.from_user.id, sys_prompt=new_val)
    await q.answer()
    await _render(update, context, edit=True)


async def on_presets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    presets = list_presets()
    context.user_data["preset_choices"] = presets
    if not presets:
        await q.answer(t(lang, "prompt_empty"), show_alert=True)
        return
    await q.edit_message_text(t(lang, "prompt_presets_title"), reply_markup=presets_kb(presets, lang))


async def on_use_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split(":")[2])
    presets = context.user_data.get("preset_choices", [])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    if idx < len(presets):
        body = get_preset(presets[idx])
        if body:
            await upsert_user(q.from_user.id, user_prompt=body)
            await q.answer(t(lang, "prompt_preset_applied"))
    await _render(update, context, edit=True)


# ───── Edit prompt (text input) ─────
async def ask_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(t(lang, "prompt_enter"))
    return T_EDIT_PROMPT


async def got_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    await upsert_user(update.effective_user.id, user_prompt=(update.message.text or "").strip())
    await update.message.reply_text(t(lang, "prompt_saved"))
    await _render(update, context, edit=False)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


def get_prompt_handlers() -> list:
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_edit, pattern=r"^prompt:edit$")],
        states={T_EDIT_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_prompt)]},
        fallbacks=[CallbackQueryHandler(cancel, pattern=r"^menu:")],
        per_message=False,
        name="prompt_edit",
        persistent=False,
    )
    return [
        edit_conv,
        CallbackQueryHandler(show_prompt, pattern=r"^menu:prompt$"),
        CallbackQueryHandler(on_view, pattern=r"^prompt:view$"),
        CallbackQueryHandler(on_toggle_sys, pattern=r"^prompt:toggle_sys$"),
        CallbackQueryHandler(on_presets, pattern=r"^prompt:presets$"),
        CallbackQueryHandler(on_use_preset, pattern=r"^prompt:use:"),
    ]
