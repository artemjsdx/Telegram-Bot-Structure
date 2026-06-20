"""
Onboarding conversation (provider-first).

Entered by the `setup:begin` button from the /start welcome. Steps:
  provider → [api_base if required] → api_key (+verify) → model → prompt → sys-toggle → done
Credentials are stored per-provider in provider_configs, so switching providers
later never wipes them.
"""
from __future__ import annotations

import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import DEFAULT_LANG
from constants import (
    S_PROVIDER, S_API_BASE, S_API_KEY, S_MODEL, S_PROMPT, S_SYS_TOGGLE,
    PROVIDER_ORDER, PAGE_SIZE_MODELS,
)
from core.ai_client import verify, fetch_models
from db.storage import get_user, upsert_user, upsert_provider_config
from handlers.menu import send_main_menu
from keyboards.factory import PROVIDER_LABELS
from providers import get_provider
from texts import t

log = logging.getLogger(__name__)


def _lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("setup_lang", DEFAULT_LANG)


def _provider_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(PROVIDER_LABELS.get(p, p), callback_data=f"setup:prov:{p}")]
            for p in PROVIDER_ORDER]
    return InlineKeyboardMarkup(rows)


def _model_kb(models: list[str]) -> InlineKeyboardMarkup:
    rows = []
    chunk = list(enumerate(models))[:PAGE_SIZE_MODELS]
    for i in range(0, len(chunk), 2):
        row = [InlineKeyboardButton(chunk[i][1], callback_data=f"setup:model:{chunk[i][0]}")]
        if i + 1 < len(chunk):
            row.append(InlineKeyboardButton(chunk[i + 1][1], callback_data=f"setup:model:{chunk[i + 1][0]}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _sys_kb(enabled: bool, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            t(lang, "settings_sys_on") if enabled else t(lang, "settings_sys_off"),
            callback_data="setup:sys")],
        [InlineKeyboardButton("🚀 " + t(lang, "btn_yes"), callback_data="setup:done")],
    ])


# ───── Steps ─────
async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data.clear()
    context.user_data["setup_lang"] = lang
    context.user_data["sys_enabled"] = True
    await q.edit_message_text(
        t(lang, "provider_title", active="—"), parse_mode=ParseMode.HTML,
        reply_markup=_provider_kb(),
    )
    return S_PROVIDER


async def on_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    provider = q.data.split(":")[2]
    context.user_data["provider"] = provider
    prov = get_provider(provider)

    if provider == "freemodel":
        await q.message.reply_text(t(lang, "provider_freemodel_warn"))

    if prov.requires_api_base() and not prov.default_api_base():
        await q.edit_message_text(t(lang, "provider_enter_base"), parse_mode=ParseMode.HTML)
        return S_API_BASE

    context.user_data["api_base"] = prov.default_api_base()
    await q.edit_message_text(t(lang, "provider_enter_key"), parse_mode=ParseMode.HTML)
    return S_API_KEY


async def on_api_base(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    url = (update.message.text or "").strip().rstrip("/")
    if not url.startswith("http"):
        await update.message.reply_text(t(lang, "provider_enter_base"))
        return S_API_BASE
    context.user_data["api_base"] = url
    await update.message.reply_text(t(lang, "provider_enter_key"))
    return S_API_KEY


async def on_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    key = (update.message.text or "").strip()
    provider = context.user_data["provider"]
    api_base = context.user_data.get("api_base", "") or get_provider(provider).default_api_base()
    status = await update.message.reply_text(t(lang, "provider_verifying"))

    try:
        await verify(provider, api_base, key)
    except Exception as e:
        await status.edit_text(t(lang, "provider_key_fail", error=str(e)[:300]))
        return S_API_KEY

    context.user_data["api_key"] = key
    context.user_data["api_base"] = api_base
    try:
        models = await fetch_models(provider, api_base, key)
    except Exception:
        models = []
    if not models:
        models = [context.user_data.get("model_id") or "default"]
    context.user_data["models"] = models

    await status.edit_text(
        t(lang, "provider_key_ok") + "\n\n" + t(lang, "provider_choose_model"),
        reply_markup=_model_kb(models),
    )
    return S_MODEL


async def on_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    idx = int(q.data.split(":")[2])
    models = context.user_data.get("models", [])
    model = models[idx] if idx < len(models) else ""
    context.user_data["model_id"] = model
    await q.edit_message_text(
        t(lang, "provider_model_set", model=model) + "\n\n" + t(lang, "prompt_enter"),
        parse_mode=ParseMode.HTML,
    )
    return S_PROMPT


async def on_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    context.user_data["user_prompt"] = (update.message.text or "").strip()
    await update.message.reply_text(
        t(lang, "settings_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=_sys_kb(context.user_data["sys_enabled"], lang),
    )
    return S_SYS_TOGGLE


async def on_sys_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data["sys_enabled"] = not context.user_data.get("sys_enabled", True)
    await q.edit_message_reply_markup(_sys_kb(context.user_data["sys_enabled"], lang))
    return S_SYS_TOGGLE


async def on_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    ud = context.user_data
    provider = ud.get("provider", "favoriteapi")

    existing = await get_user(user_id)
    await upsert_user(
        user_id,
        provider=provider,
        user_prompt=ud.get("user_prompt", ""),
        sys_prompt=1 if ud.get("sys_enabled", True) else 0,
        setup_done=1,
        lang=(existing or {}).get("lang") or DEFAULT_LANG,
        created_at=(existing or {}).get("created_at") or int(time.time()),
    )
    await upsert_provider_config(
        user_id, provider,
        api_base=ud.get("api_base", ""),
        api_key=ud.get("api_key", ""),
        model_id=ud.get("model_id", ""),
    )

    lang = _lang(context)
    context.user_data.clear()
    await q.edit_message_text(t(lang, "channel_add_howto"), parse_mode=ParseMode.HTML)
    await send_main_menu(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    context.user_data.clear()
    await update.message.reply_text(t(lang, "cancelled"))
    return ConversationHandler.END


def get_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(begin, pattern=r"^setup:begin$")],
        states={
            S_PROVIDER: [CallbackQueryHandler(on_provider, pattern=r"^setup:prov:")],
            S_API_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_api_base)],
            S_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_api_key)],
            S_MODEL: [CallbackQueryHandler(on_model, pattern=r"^setup:model:")],
            S_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_prompt)],
            S_SYS_TOGGLE: [
                CallbackQueryHandler(on_sys_toggle, pattern=r"^setup:sys$"),
                CallbackQueryHandler(on_done, pattern=r"^setup:done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
        name="onboarding",
        persistent=False,
    )
