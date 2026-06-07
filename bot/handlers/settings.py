import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from db.storage import get_user, upsert_user
from core.ai_client import verify_key, get_models

logger = logging.getLogger(__name__)

EDIT_PROMPT = 20
EDIT_API_BASE = 21
EDIT_API_KEY = 22
CHOOSE_NEW_MODEL = 23

FALLBACK_MODELS = [
    "gemini-3.0-flash-thinking",
    "gemini-3.0-flash",
    "gemini-2.5-flash-thinking",
    "gemini-2.5-flash",
    "gemini-2.5-mini",
]


def _settings_text(user: dict) -> str:
    sys_on = bool(user.get("sys_prompt", 1))
    chan = user.get("chan_title") or "не привязан"
    prompt = user.get("user_prompt", "")
    prompt_preview = (prompt[:70] + "...") if len(prompt) > 70 else prompt
    model = user.get("model_id", "—")
    api_base = user.get("api_base", "—")

    return (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"🌐 API URL: <code>{api_base}</code>\n"
        f"🤖 Модель: <code>{model}</code>\n"
        f"📣 Канал: {chan}\n"
        f"✏️ Промпт: <i>{prompt_preview or 'не задан'}</i>\n"
        f"🎨 Сист. промпт: {'ВКЛ ✅' if sys_on else 'ВЫКЛ ❌'}\n"
    )


def _settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    sys_on = bool(user.get("sys_prompt", 1))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if sys_on else '❌'} Системный промпт",
            callback_data="s:toggle_sys",
        )],
        [InlineKeyboardButton("✏️ Изменить промпт", callback_data="s:edit_prompt")],
        [InlineKeyboardButton("🤖 Изменить модель", callback_data="s:edit_model")],
        [InlineKeyboardButton("🔑 Изменить API ключ", callback_data="s:edit_key")],
        [InlineKeyboardButton("🌐 Изменить API URL", callback_data="s:edit_base")],
        [InlineKeyboardButton("📣 Привязать другой канал", callback_data="s:rebind")],
        [InlineKeyboardButton("⏹ Отвязать канал", callback_data="s:unbind")],
    ])


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user or not user.get("setup_done"):
        await update.message.reply_text("❌ Сначала пройди настройку: /start")
        return ConversationHandler.END

    await update.message.reply_html(
        _settings_text(user),
        reply_markup=_settings_keyboard(user),
    )
    return ConversationHandler.END


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    action = query.data.replace("s:", "")
    user = await get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Пользователь не найден. /start")
        return ConversationHandler.END

    if action == "toggle_sys":
        new_val = 0 if user.get("sys_prompt", 1) else 1
        await upsert_user(user_id, sys_prompt=new_val)
        user = await get_user(user_id)
        await query.edit_message_text(
            _settings_text(user),
            parse_mode="HTML",
            reply_markup=_settings_keyboard(user),
        )
        return ConversationHandler.END

    if action == "edit_prompt":
        await query.edit_message_text("✏️ Введи новый промпт:")
        return EDIT_PROMPT

    if action == "edit_key":
        await query.edit_message_text("🔑 Введи новый API ключ (fa_sk_...):")
        return EDIT_API_KEY

    if action == "edit_base":
        await query.edit_message_text("🌐 Введи новый URL FavoriteAPI:")
        return EDIT_API_BASE

    if action == "edit_model":
        try:
            models = await get_models(user["api_base"], user["api_key"])
            if not models:
                models = FALLBACK_MODELS
        except Exception:
            models = FALLBACK_MODELS

        keyboard = []
        for i in range(0, len(models[:12]), 2):
            row = [InlineKeyboardButton(models[i], callback_data=f"snm:{models[i]}")]
            if i + 1 < len(models):
                row.append(InlineKeyboardButton(models[i + 1], callback_data=f"snm:{models[i + 1]}"))
            keyboard.append(row)
        await query.edit_message_text(
            "🤖 Выбери новую модель:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_NEW_MODEL

    if action == "unbind":
        await upsert_user(user_id, channel_id=None, chan_title=None)
        await query.edit_message_text("✅ Канал отвязан. Мониторинг остановлен.")
        return ConversationHandler.END

    if action == "rebind":
        await query.edit_message_text(
            "Используй /bind_channel для привязки нового канала."
        )
        return ConversationHandler.END

    return ConversationHandler.END


async def got_new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await upsert_user(update.effective_user.id, user_prompt=update.message.text.strip())
    await update.message.reply_text("✅ Промпт обновлён!")
    return ConversationHandler.END


async def got_new_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_key = update.message.text.strip()
    user = await get_user(user_id)
    try:
        await verify_key(user["api_base"], new_key)
        await upsert_user(user_id, api_key=new_key)
        await update.message.reply_text("✅ API ключ обновлён!")
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\nКлюч не сохранён. Введи снова:"
        )
        return EDIT_API_KEY


async def got_new_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_base = update.message.text.strip().rstrip("/")
    await upsert_user(update.effective_user.id, api_base=new_base)
    await update.message.reply_text("✅ API URL обновлён!")
    return ConversationHandler.END


async def new_model_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model = query.data.replace("snm:", "")
    await upsert_user(query.from_user.id, model_id=model)
    await query.edit_message_text(
        f"✅ Модель изменена: <b>{model}</b>", parse_mode="HTML"
    )
    return ConversationHandler.END


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено. /settings — открыть настройки.")
    return ConversationHandler.END


def get_settings_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("settings", settings_command),
            CallbackQueryHandler(settings_callback, pattern="^s:"),
        ],
        states={
            EDIT_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_prompt)],
            EDIT_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_key)],
            EDIT_API_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_base)],
            CHOOSE_NEW_MODEL: [CallbackQueryHandler(new_model_chosen, pattern="^snm:")],
        },
        fallbacks=[CommandHandler("cancel", cancel_settings)],
        per_message=False,
        name="settings_conversation",
        persistent=False,
    )
