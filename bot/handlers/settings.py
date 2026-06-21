"""
Settings section: system-prompt toggle, preview-mode toggle, language switch,
and statistics reset.
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from db.storage import get_user, upsert_user, reset_stats_for_user
from handlers.menu import nav
from keyboards.factory import settings_kb, language_kb, confirm_kb
from texts import t


async def _render(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    text = t(lang, "settings_title")
    kb = settings_kb(user or {}, lang)
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _render(update, context, edit=False)


async def on_toggle_sys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = await get_user(q.from_user.id)
    await upsert_user(q.from_user.id, sys_prompt=0 if (user or {}).get("sys_prompt", 1) else 1)
    await q.answer()
    await _render(update, context, edit=True)


async def on_toggle_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = await get_user(q.from_user.id)
    await upsert_user(q.from_user.id, preview_mode=0 if (user or {}).get("preview_mode", 0) else 1)
    await q.answer()
    await _render(update, context, edit=True)


async def on_toggle_shares(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = await get_user(q.from_user.id)
    await upsert_user(q.from_user.id, accept_presets=0 if (user or {}).get("accept_presets", 1) else 1)
    await q.answer()
    await _render(update, context, edit=True)


async def on_lang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(
        t(lang, "settings_title"), parse_mode=ParseMode.HTML,
        reply_markup=language_kb(lang, lang),
    )


async def on_lang_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    new_lang = q.data.split(":")[1]
    await upsert_user(q.from_user.id, lang=new_lang)
    await q.answer(t(new_lang, "settings_saved"))
    await _render(update, context, edit=True)


async def on_reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(
        t(lang, "settings_reset_stats") + " ?",
        reply_markup=confirm_kb("s:reset_stats_yes", "menu:settings", lang),
    )


async def on_reset_stats_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await reset_stats_for_user(q.from_user.id)
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.answer(t(lang, "settings_stats_reset"))
    await _render(update, context, edit=True)


def get_settings_handlers() -> list:
    return [
        CallbackQueryHandler(show_settings, pattern=r"^menu:settings$"),
        CallbackQueryHandler(on_toggle_sys, pattern=r"^s:toggle_sys$"),
        CallbackQueryHandler(on_toggle_preview, pattern=r"^s:toggle_preview$"),
        CallbackQueryHandler(on_toggle_shares, pattern=r"^s:toggle_shares$"),
        CallbackQueryHandler(on_lang_menu, pattern=r"^s:lang$"),
        CallbackQueryHandler(on_reset_stats_yes, pattern=r"^s:reset_stats_yes$"),
        CallbackQueryHandler(on_reset_stats, pattern=r"^s:reset_stats$"),
        CallbackQueryHandler(on_lang_set, pattern=r"^lang:(ru|en)$"),
    ]
