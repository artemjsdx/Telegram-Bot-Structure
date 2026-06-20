"""
Provider section: pick the active provider (2 taps, credentials persist per
provider), test the connection, and change model / key / base.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from constants import T_EDIT_KEY, T_EDIT_BASE
from core.ai_client import resolve_creds, verify, fetch_models
from db.storage import get_user, upsert_user, get_provider_configs, upsert_provider_config
from handlers.menu import nav
from keyboards.factory import provider_kb, model_kb, PROVIDER_LABELS
from providers import get_provider
from texts import t

log = logging.getLogger(__name__)


async def _render(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    current = (user or {}).get("provider") or "favoriteapi"
    configs = await get_provider_configs(update.effective_user.id)
    text = t(lang, "provider_title", active=PROVIDER_LABELS.get(current, current))
    kb = provider_kb(current, configs, lang)
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


async def show_providers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Entered from the (possibly media) main menu — delete + send fresh text.
    await _render(update, context, edit=False)


async def on_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    name = q.data.split(":")[2]
    await upsert_user(q.from_user.id, provider=name)
    configs = await get_provider_configs(q.from_user.id)
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    if not configs.get(name, {}).get("api_key"):
        await q.answer(t(lang, "provider_need_creds", name=PROVIDER_LABELS.get(name, name)))
    else:
        await q.answer(t(lang, "provider_switched", name=PROVIDER_LABELS.get(name, name)))
    await _render(update, context, edit=True)


async def on_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    creds = await resolve_creds(user)
    await q.answer(t(lang, "provider_verifying"))
    try:
        info = await verify(creds["provider"], creds["api_base"], creds["api_key"])
        await q.answer(t(lang, "provider_test_ok", info=str(info)[:180]), show_alert=True)
    except Exception as e:
        await q.answer(t(lang, "provider_test_fail", error=str(e)[:180]), show_alert=True)


async def on_setmodel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    creds = await resolve_creds(user)
    try:
        models = await fetch_models(creds["provider"], creds["api_base"], creds["api_key"])
    except Exception:
        models = []
    if not models:
        models = [creds["model"] or "default"]
    context.user_data["model_choices"] = models
    await q.edit_message_text(
        t(lang, "provider_choose_model"),
        reply_markup=model_kb(models, 0, lang),
    )


async def on_model_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    page = int(q.data.split(":")[1])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    models = context.user_data.get("model_choices", [])
    await q.edit_message_reply_markup(model_kb(models, page, lang))


async def on_model_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split(":")[1])
    models = context.user_data.get("model_choices", [])
    model = models[idx] if idx < len(models) else ""
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    provider = (user or {}).get("provider") or "favoriteapi"
    await upsert_provider_config(q.from_user.id, provider, model_id=model)
    await q.answer(t(lang, "provider_model_set", model=model))
    await _render(update, context, edit=True)


# ───── Text-input flows: change key / base ─────
async def ask_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(t(lang, "provider_enter_key"))
    return T_EDIT_KEY


async def got_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    provider = (user or {}).get("provider") or "favoriteapi"
    key = (update.message.text or "").strip()
    creds = await resolve_creds(user)
    try:
        await verify(provider, creds["api_base"], key)
    except Exception as e:
        await update.message.reply_text(t(lang, "provider_key_fail", error=str(e)[:300]))
        return T_EDIT_KEY
    await upsert_provider_config(update.effective_user.id, provider, api_key=key)
    await update.message.reply_text(t(lang, "provider_key_ok"))
    await _render(update, context, edit=False)
    return ConversationHandler.END


async def ask_base(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or "ru"
    await q.edit_message_text(t(lang, "provider_enter_base"))
    return T_EDIT_BASE


async def got_base(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or "ru"
    provider = (user or {}).get("provider") or "favoriteapi"
    base = (update.message.text or "").strip().rstrip("/")
    await upsert_provider_config(update.effective_user.id, provider, api_base=base)
    await update.message.reply_text(t(lang, "settings_saved"))
    await _render(update, context, edit=False)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


def get_provider_handlers() -> list:
    creds_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_key, pattern=r"^prov:setkey$"),
            CallbackQueryHandler(ask_base, pattern=r"^prov:setbase$"),
        ],
        states={
            T_EDIT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_key)],
            T_EDIT_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_base)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern=r"^menu:")],
        per_message=False,
        name="provider_creds",
        persistent=False,
    )
    return [
        creds_conv,
        CallbackQueryHandler(show_providers, pattern=r"^menu:provider$"),
        CallbackQueryHandler(on_switch, pattern=r"^prov:set:"),
        CallbackQueryHandler(on_test, pattern=r"^prov:test$"),
        CallbackQueryHandler(on_setmodel, pattern=r"^prov:setmodel$"),
        CallbackQueryHandler(on_model_page, pattern=r"^modelpage:"),
        CallbackQueryHandler(on_model_pick, pattern=r"^model:"),
    ]
