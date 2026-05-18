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

ASK_API_BASE = 0
ASK_API_KEY = 1
CHOOSE_MODEL = 2
ASK_PROMPT = 3
CONFIRM_SETUP = 4

FALLBACK_MODELS = [
    "gemini-3.0-flash-thinking",
    "gemini-3.0-flash",
    "gemini-2.5-flash-thinking",
    "gemini-2.5-flash",
    "gemini-2.5-mini-thinking",
    "gemini-2.5-mini",
]


def _model_keyboard(models: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(0, len(models[:12]), 2):
        row = [InlineKeyboardButton(models[i], callback_data=f"model:{models[i]}")]
        if i + 1 < len(models):
            row.append(
                InlineKeyboardButton(models[i + 1], callback_data=f"model:{models[i + 1]}")
            )
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if user and user.get("setup_done"):
        chan = user.get("chan_title") or "не привязан"
        await update.message.reply_html(
            "✅ <b>Бот уже настроен!</b>\n\n"
            f"🔑 Ключ: <code>...{user['api_key'][-8:]}</code>\n"
            f"🤖 Модель: <code>{user['model_id']}</code>\n"
            f"📣 Канал: {chan}\n\n"
            "⚙️ /settings — настройки\n"
            "📣 /bind_channel — привязать канал\n"
            "📊 /status — статус"
        )
        return ConversationHandler.END

    await update.message.reply_html(
        "👋 <b>Channel AI Bot</b>\n\n"
        "Бот переписывает посты в твоём Telegram-канале "
        "с помощью ИИ (FavoriteAPI / Gemini).\n\n"
        "━━━ Шаг 1 из 4 ━━━\n\n"
        "🌐 Введи <b>базовый URL FavoriteAPI</b>\n\n"
        "Примеры:\n"
        "• <code>http://192.168.1.10:8000</code>\n"
        "• <code>https://xxxx.trycloudflare.com</code>\n\n"
        "Если сервер запущен локально — укажи его адрес."
    )
    return ASK_API_BASE


async def got_api_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await update.message.reply_text(
            "❌ URL должен начинаться с http:// или https://\nПопробуй снова:"
        )
        return ASK_API_BASE

    context.user_data["api_base"] = url
    await update.message.reply_html(
        "✅ URL сохранён!\n\n"
        "━━━ Шаг 2 из 4 ━━━\n\n"
        "🔑 Введи <b>API ключ FavoriteAPI</b>\n"
        "Формат: <code>fa_sk_...</code>"
    )
    return ASK_API_KEY


async def got_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip()
    api_base = context.user_data.get("api_base", "")
    msg = await update.message.reply_text("⏳ Проверяю ключ...")

    try:
        info = await verify_key(api_base, key)
        context.user_data["api_key"] = key

        try:
            models = await get_models(api_base, key)
            if not models:
                models = FALLBACK_MODELS
        except Exception:
            models = FALLBACK_MODELS

        context.user_data["models"] = models

        key_name = info.get("key", {}).get("name", "")
        ctx_kb = info.get("key", {}).get("context_kb", 0)
        def_model = info.get("service", {}).get("default_model_id", "")

        await msg.edit_text(
            f"✅ Ключ валиден! {f'({key_name})' if key_name else ''}\n"
            f"Контекст использован: {ctx_kb:.1f} KB\n"
            f"Модель по умолчанию: {def_model or '—'}\n\n"
            "━━━ Шаг 3 из 4 ━━━\n\n"
            "🤖 Выбери модель ИИ:",
            reply_markup=_model_keyboard(models),
            parse_mode="HTML",
        )
        return CHOOSE_MODEL

    except Exception as e:
        await msg.edit_text(
            f"❌ Ошибка проверки ключа:\n<code>{e}</code>\n\n"
            "Проверь URL и ключ, попробуй снова:",
            parse_mode="HTML",
        )
        return ASK_API_KEY


async def model_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model = query.data.replace("model:", "")
    context.user_data["model_id"] = model

    await query.edit_message_text(
        f"✅ Модель выбрана: <b>{model}</b>\n\n"
        "━━━ Шаг 4 из 4 ━━━\n\n"
        "✏️ Введи свой <b>промпт</b> для обработки постов\n\n"
        "<i>Пример:\nПерепиши этот пост в стиле tech-блога. "
        "Сохрани смысл, улучши структуру, используй Telegram HTML-форматирование.</i>",
        parse_mode="HTML",
    )
    return ASK_PROMPT


async def got_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    context.user_data["user_prompt"] = prompt
    sys_enabled = context.user_data.get("sys_prompt_enabled", True)

    await update.message.reply_html(
        "✅ Промпт сохранён!\n\n"
        "<b>Системный промпт форматирования</b> — встроенные инструкции, "
        "которые обучают ИИ использовать Telegram HTML-теги "
        "(<b>жирный</b>, <i>курсив</i>, <u>подчёркивание</u>, цитаты, "
        "спойлеры и т.д.).\n\n"
        "Рекомендуется <b>включить</b> для красиво оформленных постов.",
        reply_markup=_sys_prompt_keyboard(sys_enabled),
    )
    return CONFIRM_SETUP


def _sys_prompt_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if enabled else '❌'} Системный промпт форматирования",
            callback_data="toggle_sys",
        )],
        [InlineKeyboardButton("🚀 Завершить настройку", callback_data="setup_done")],
    ])


async def toggle_sys_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = context.user_data.get("sys_prompt_enabled", True)
    context.user_data["sys_prompt_enabled"] = not current
    await query.edit_message_reply_markup(
        _sys_prompt_keyboard(context.user_data["sys_prompt_enabled"])
    )
    return CONFIRM_SETUP


async def setup_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    await upsert_user(
        user_id,
        api_base=context.user_data.get("api_base", ""),
        api_key=context.user_data.get("api_key", ""),
        model_id=context.user_data.get("model_id", ""),
        user_prompt=context.user_data.get("user_prompt", ""),
        sys_prompt=1 if context.user_data.get("sys_prompt_enabled", True) else 0,
        setup_done=1,
    )

    await query.edit_message_text(
        "🎉 <b>Настройка завершена!</b>\n\n"
        "Осталось привязать канал:\n\n"
        "1. Добавь бота в канал как <b>администратора</b>\n"
        "   (права: публикация, редактирование, удаление сообщений)\n\n"
        "2. Отправь /bind_channel\n\n"
        "3. Перешли любой пост из своего канала\n\n"
        "После этого бот начнёт переписывать новые посты! 🚀",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Настройка отменена. /start — начать заново.")
    return ConversationHandler.END


def get_setup_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_API_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_api_base)],
            ASK_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_api_key)],
            CHOOSE_MODEL: [CallbackQueryHandler(model_chosen, pattern="^model:")],
            ASK_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_prompt)],
            CONFIRM_SETUP: [
                CallbackQueryHandler(toggle_sys_prompt, pattern="^toggle_sys$"),
                CallbackQueryHandler(setup_done, pattern="^setup_done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
        name="setup_conversation",
        persistent=False,
    )
