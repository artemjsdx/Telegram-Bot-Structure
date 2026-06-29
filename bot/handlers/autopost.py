"""
Autoposting UI: link a Telegram user account (MTProto), pick sources & targets,
choose a mode (forward / structure / digest), tune anti-ban settings, and manage a
separate autopost prompt library — all per agent.

Self-contained i18n table (_T) keeps this large subsystem's strings out of the
shared texts.py. Entity resolution and channel joining go through the linked
account's Telethon client (core.tg_client).
"""
from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from config import DEFAULT_LANG
from constants import (
    AP_API_ID, AP_API_HASH, AP_PHONE, AP_CODE, AP_2FA,
    AP_ADD_SOURCE, AP_ADD_TARGET, AP_PROMPT, AP_PRESET_NEW,
)
from core import tg_client
from db.storage import (
    get_user, get_agent,
    create_account, get_account, delete_account, update_account,
    get_or_create_config, update_config,
    add_source, get_sources, remove_source,
    add_target, get_targets, remove_target,
    create_autopost_preset, get_autopost_presets, get_autopost_preset,
    delete_autopost_preset,
)
from handlers.menu import nav
from keyboards.factory import back_btn, home_btn

log = logging.getLogger(__name__)

# ───── local i18n ─────
_T = {
    "ru": {
        "ap_btn": "📤 Автопостинг",
        "ap_title": (
            "📤 <b>Автопостинг</b> — {name}\n\n"
            "Аккаунт: <b>{account}</b>\n"
            "Режим: <b>{mode}</b>\n"
            "Источников: <b>{nsrc}</b> · Целей: <b>{ntgt}</b>\n"
            "Состояние: <b>{state}</b>\n\n"
            "<blockquote>Постит от вашего Telegram-аккаунта (не бота): пересылка, "
            "ИИ-структурирование или тема-дайджест из нескольких сообщений. Дата МСК и "
            "веб-поиск берутся из настроек агента.</blockquote>"
        ),
        "ap_mode_forward": "↪️ Пересылка",
        "ap_mode_structure": "✍️ Структурирование",
        "ap_mode_digest": "🧵 Тема-дайджест",
        "ap_state_on": "🟢 включён",
        "ap_state_off": "🔴 выключен",
        "ap_no_account": "не привязан",
        "ap_btn_account": "👤 Аккаунт",
        "ap_btn_mode": "🔀 Режим: {mode}",
        "ap_btn_sources": "📥 Источники ({n})",
        "ap_btn_targets": "📤 Цели ({n})",
        "ap_btn_settings": "⚙️ Анти-бан и лимиты",
        "ap_btn_prompt": "✏️ Промпт автопостинга",
        "ap_btn_enable": "🟢 Включить",
        "ap_btn_disable": "🔴 Выключить",
        "ap_enable_blocked": "⚠️ Нужны аккаунт, хотя бы один источник и одна цель.",
        # account
        "ap_acc_title": (
            "👤 <b>Аккаунт автопостинга</b>\n\n{status}\n\n"
            "<blockquote>Нужны api_id и api_hash с my.telegram.org. Вход: api_id → "
            "api_hash → телефон → код из Telegram → пароль 2FA (если есть). Сессия "
            "хранится зашифрованной строкой в БД.</blockquote>"
        ),
        "ap_acc_linked": "Привязан: <b>{nick}</b> (тел. {phone}).",
        "ap_acc_none": "Аккаунт ещё не привязан.",
        "ap_acc_login": "🔑 Войти / привязать",
        "ap_acc_relogin": "🔁 Перепривязать",
        "ap_acc_del": "🗑 Отвязать аккаунт",
        "ap_no_telethon": "⚠️ Telethon не установлен на сервере — автопостинг недоступен.",
        "ap_ask_api_id": "1/4 Пришлите <b>api_id</b> (число с my.telegram.org):",
        "ap_ask_api_hash": "2/4 Пришлите <b>api_hash</b>:",
        "ap_ask_phone": "3/4 Пришлите номер телефона в формате <code>+79991234567</code>:",
        "ap_ask_code": (
            "4/4 Код отправлен в Telegram аккаунта. Пришлите его.\n"
            "<blockquote>Совет: вводите код с пробелом или дефисом между цифрами "
            "(<code>1 2 3 4 5</code>), чтобы Telegram не «съел» его как ссылку.</blockquote>"
        ),
        "ap_ask_2fa": "🔒 У аккаунта включён облачный пароль (2FA). Пришлите его:",
        "ap_login_ok": "✅ Аккаунт привязан: <b>{nick}</b>.",
        "ap_login_err": "❌ Не удалось войти: {err}",
        "ap_bad_api_id": "Это не похоже на число. Пришлите api_id ещё раз:",
        # sources / targets
        "ap_src_title": (
            "📥 <b>Источники</b>\n\n{list}\n\n"
            "<blockquote>Добавьте канал/чат: перешлите оттуда любое сообщение, либо "
            "пришлите @username, ссылку t.me или id. Аккаунт подпишется на него.</blockquote>"
        ),
        "ap_tgt_title": (
            "📤 <b>Цели публикации</b>\n\n{list}\n\n"
            "<blockquote>Куда публиковать. Аккаунт должен быть участником/админом цели. "
            "Перешлите сообщение из цели, либо пришлите @username, ссылку или id.</blockquote>"
        ),
        "ap_empty": "— пусто —",
        "ap_add": "➕ Добавить",
        "ap_add_ask_src": (
            "📥 <b>Добавить источник</b>\n\n"
            "Пришлите канал/чат одним из способов:\n"
            "• перешлите сюда любое сообщение из него;\n"
            "• или пришлите <code>@username</code>, ссылку <code>t.me/...</code> или числовой id.\n\n"
            "<blockquote>Аккаунт автоматически подпишется на источник, чтобы читать новые "
            "сообщения.</blockquote>"
        ),
        "ap_add_ask_tgt": (
            "📤 <b>Добавить цель</b>\n\n"
            "Пришлите канал/чат, КУДА публиковать:\n"
            "• перешлите сюда любое сообщение из него;\n"
            "• или пришлите <code>@username</code>, ссылку <code>t.me/...</code> или числовой id.\n\n"
            "<blockquote>Привязанный аккаунт должен быть участником цели, а для каналов — "
            "с правом публикации (админом).</blockquote>"
        ),
        "ap_need_account_first": "⚠️ Сначала привяжите аккаунт.",
        "ap_resolve_fail": "❌ Не удалось распознать/получить доступ. Проверьте ссылку и что аккаунт имеет доступ.",
        "ap_added": "✅ Добавлено: {title}",
        # settings
        "ap_set_title": (
            "⚙️ <b>Анти-бан и лимиты</b>\n\n"
            "Интервал опроса: <b>{interval}</b> сек\n"
            "Разброс (джиттер): <b>{jitter}</b> сек\n"
            "Лимит постов за окно: <b>{cap}</b>\n"
            "Окно лимита: <b>{window}</b> сек\n"
            "Размер дайджеста: <b>{digest}</b> сообщений\n"
            "Помнить последних постов: <b>{editn}</b>\n\n"
            "<blockquote>Реже и со случайным разбросом = безопаснее для аккаунта. "
            "Лимит «0» — без ограничения за окно.</blockquote>"
        ),
        "ap_set_interval": "⏱ Интервал: {n} сек",
        "ap_set_jitter": "🎲 Джиттер: {n} сек",
        "ap_set_cap": "🚧 Лимит/окно: {n}",
        "ap_set_window": "🪟 Окно: {n} сек",
        "ap_set_digest": "🧵 Дайджест: {n}",
        "ap_set_editn": "🧠 Память постов: {n}",
        # prompt + library
        "ap_prompt_title": "✏️ <b>Промпт автопостинга</b>\n\n<blockquote>{body}</blockquote>",
        "ap_prompt_empty": "Промпт ещё не задан.",
        "ap_prompt_edit": "✏️ Изменить",
        "ap_prompt_lib": "📚 Библиотека",
        "ap_prompt_ask": "Пришлите текст промпта для автопостинга:",
        "ap_lib_title": "📚 <b>Библиотека автопостинга</b>\n\nВыберите пресет или создайте свой.",
        "ap_lib_new": "➕ Создать пресет",
        "ap_lib_new_ask": "Пришлите название и текст пресета одним сообщением (первая строка — название):",
        "ap_lib_applied": "✅ Пресет применён.",
        "ap_lib_empty": "Пока нет сохранённых пресетов.",
        "ap_saved": "✅ Сохранено.",
    },
    "en": {},  # falls back to ru for this subsystem
}


def _lang(user: dict | None) -> str:
    return (user or {}).get("lang") or DEFAULT_LANG


def T(lang: str, key: str, **kw) -> str:
    s = _T.get(lang, {}).get(key) or _T["ru"].get(key, key)
    return s.format(**kw) if kw else s


_MODE_LABEL = {"forward": "ap_mode_forward", "structure": "ap_mode_structure", "digest": "ap_mode_digest"}
_MODE_ORDER = ["forward", "structure", "digest"]

_STEPS = {
    "poll_interval": [30, 60, 120, 300, 600],
    "jitter": [0, 5, 15, 30, 60],
    "max_per_window": [0, 5, 10, 20, 50],
    "window_sec": [600, 1800, 3600, 7200, 86400],
    "digest_size": [30, 50, 100, 200, 300],
    "edit_last_n": [0, 5, 10, 20],
}


def _cycle(field: str, current) -> int:
    steps = _STEPS[field]
    try:
        return steps[(steps.index(int(current)) + 1) % len(steps)]
    except (ValueError, TypeError):
        return steps[0]


# ═══════════ config screen ═══════════
async def _render_config(update, context, aid: int) -> None:
    user = await get_user(update.effective_user.id)
    lang = _lang(user)
    agent = await get_agent(aid)
    if not agent:
        return
    cfg = await get_or_create_config(aid, agent["user_id"])
    account = await get_account(cfg["account_id"]) if cfg.get("account_id") else None
    sources = await get_sources(cfg["config_id"])
    targets = await get_targets(cfg["config_id"])
    mode = cfg.get("mode") or "forward"
    enabled = bool(cfg.get("enabled"))

    text = T(lang, "ap_title",
             name=agent.get("name") or f"#{aid}",
             account=(account.get("nickname") if account else T(lang, "ap_no_account")),
             mode=T(lang, _MODE_LABEL[mode]),
             nsrc=len(sources), ntgt=len(targets),
             state=T(lang, "ap_state_on" if enabled else "ap_state_off"))

    rows = [
        [InlineKeyboardButton(T(lang, "ap_btn_account"), callback_data=f"ap:acc:{aid}"),
         InlineKeyboardButton(T(lang, "ap_btn_mode", mode=T(lang, _MODE_LABEL[mode])),
                              callback_data=f"ap:mode:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_btn_sources", n=len(sources)), callback_data=f"ap:srcs:{aid}"),
         InlineKeyboardButton(T(lang, "ap_btn_targets", n=len(targets)), callback_data=f"ap:tgts:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_btn_settings"), callback_data=f"ap:set:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_btn_prompt"), callback_data=f"ap:prompt:{aid}")],
    ]
    can_enable = account and sources and targets
    if enabled:
        rows.append([InlineKeyboardButton(T(lang, "ap_btn_disable"), callback_data=f"ap:toggle:{aid}")])
    elif can_enable:
        rows.append([InlineKeyboardButton(T(lang, "ap_btn_enable"), callback_data=f"ap:toggle:{aid}")])
    rows.append([back_btn(f"agent:view:{aid}", lang), home_btn(lang)])
    await _show(update, context, text, InlineKeyboardMarkup(rows))


async def _show(update, context, text, kb) -> None:
    q = update.callback_query
    if q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


async def open_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await _render_config(update, context, int(q.data.split(":")[2]))


async def cycle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    cfg = await get_config_for_agent(aid)
    if cfg:
        cur = cfg.get("mode") or "forward"
        nxt = _MODE_ORDER[(_MODE_ORDER.index(cur) + 1) % len(_MODE_ORDER)]
        await update_config(cfg["config_id"], mode=nxt)
    await _render_config(update, context, aid)


async def toggle_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    aid = int(q.data.split(":")[2])
    cfg = await get_config_for_agent(aid)
    if not cfg:
        await q.answer()
        return
    if not cfg.get("enabled"):
        account = await get_account(cfg["account_id"]) if cfg.get("account_id") else None
        if not (account and await get_sources(cfg["config_id"]) and await get_targets(cfg["config_id"])):
            await q.answer(T(_lang(await get_user(q.from_user.id)), "ap_enable_blocked"), show_alert=True)
            return
    await q.answer()
    await update_config(cfg["config_id"], enabled=0 if cfg.get("enabled") else 1)
    await _render_config(update, context, aid)


async def get_config_for_agent(aid: int) -> dict | None:
    agent = await get_agent(aid)
    if not agent:
        return None
    return await get_or_create_config(aid, agent["user_id"])


# ═══════════ account screen + login ═══════════
async def _render_account(update, context, aid: int) -> None:
    user = await get_user(update.effective_user.id)
    lang = _lang(user)
    cfg = await get_config_for_agent(aid)
    account = await get_account(cfg["account_id"]) if cfg and cfg.get("account_id") else None
    if not tg_client.available():
        status = T(lang, "ap_no_telethon")
    elif account:
        status = T(lang, "ap_acc_linked", nick=account.get("nickname") or "—",
                   phone=account.get("phone") or "—")
    else:
        status = T(lang, "ap_acc_none")
    rows = []
    if tg_client.available():
        rows.append([InlineKeyboardButton(
            T(lang, "ap_acc_relogin" if account else "ap_acc_login"),
            callback_data=f"ap:login:{aid}")])
        if account:
            rows.append([InlineKeyboardButton(T(lang, "ap_acc_del"), callback_data=f"ap:accdel:{aid}")])
    rows.append([back_btn(f"ap:open:{aid}", lang), home_btn(lang)])
    await _show(update, context, T(lang, "ap_acc_title", status=status), InlineKeyboardMarkup(rows))


async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await _render_account(update, context, int(q.data.split(":")[2]))


async def account_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    cfg = await get_config_for_agent(aid)
    if cfg and cfg.get("account_id"):
        await tg_client.drop_client(cfg["account_id"])
        await delete_account(cfg["account_id"])
    await _render_account(update, context, aid)


async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = _lang(user)
    if not tg_client.available():
        await q.answer(T(lang, "ap_no_telethon"), show_alert=True)
        return ConversationHandler.END
    context.user_data["ap_aid"] = aid
    context.user_data["ap_lang"] = lang
    await q.edit_message_text(T(lang, "ap_ask_api_id"), parse_mode=ParseMode.HTML,
                              reply_markup=InlineKeyboardMarkup([[back_btn(f"ap:acc:{aid}", lang)]]))
    return AP_API_ID


async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    raw = (update.message.text or "").strip()
    if not raw.isdigit():
        await update.message.reply_html(T(lang, "ap_bad_api_id"))
        return AP_API_ID
    context.user_data["ap_api_id"] = int(raw)
    await update.message.reply_html(T(lang, "ap_ask_api_hash"))
    return AP_API_HASH


async def login_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    context.user_data["ap_api_hash"] = (update.message.text or "").strip()
    await update.message.reply_html(T(lang, "ap_ask_phone"))
    return AP_PHONE


async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    phone = (update.message.text or "").strip()
    context.user_data["ap_phone"] = phone
    uid = update.effective_user.id
    status = await tg_client.begin_login(uid, context.user_data["ap_api_id"],
                                         context.user_data["ap_api_hash"], phone)
    if status == "code_sent":
        await update.message.reply_html(T(lang, "ap_ask_code"))
        return AP_CODE
    if status == "already":
        return await _finalize_login(update, context)
    await update.message.reply_html(T(lang, "ap_login_err", err=status[6:]))
    return ConversationHandler.END


async def login_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    uid = update.effective_user.id
    code = (update.message.text or "").replace(" ", "").replace("-", "")
    status = await tg_client.confirm_code(uid, code)
    if status == "ok":
        return await _finalize_login(update, context)
    if status == "need_2fa":
        await update.message.reply_html(T(lang, "ap_ask_2fa"))
        return AP_2FA
    await update.message.reply_html(T(lang, "ap_login_err", err=status[6:]))
    return ConversationHandler.END


async def login_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    uid = update.effective_user.id
    status = await tg_client.confirm_password(uid, (update.message.text or "").strip())
    if status == "ok":
        return await _finalize_login(update, context)
    await update.message.reply_html(T(lang, "ap_login_err", err=status[6:]))
    return ConversationHandler.END


async def _finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    uid = update.effective_user.id
    aid = context.user_data.get("ap_aid")
    data = await tg_client.finish_login(uid)
    if not data:
        await update.message.reply_html(T(lang, "ap_login_err", err="session"))
        return ConversationHandler.END
    account_id = await create_account(uid, data["api_id"], data["api_hash"], data["phone"])
    await update_account(account_id, session=data["session"], nickname=data["nickname"], status="active")
    cfg = await get_config_for_agent(aid)
    if cfg:
        # Replace any previous account on this config.
        if cfg.get("account_id") and cfg["account_id"] != account_id:
            await tg_client.drop_client(cfg["account_id"])
            await delete_account(cfg["account_id"])
        await update_config(cfg["config_id"], account_id=account_id)
    await update.message.reply_html(T(lang, "ap_login_ok", nick=data["nickname"]))
    await _render_account(update, context, aid)
    return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await tg_client.cancel_login(update.effective_user.id)
    q = update.callback_query
    if q:
        await q.answer()
        await _render_account(update, context, int(q.data.split(":")[2]))
    return ConversationHandler.END


# ═══════════ sources / targets ═══════════
def _parse_ref(text: str):
    text = text.strip()
    if text.startswith("@"):
        return text
    if "t.me/" in text:
        part = text.split("t.me/", 1)[1].strip("/").split("/")[0].split("?")[0]
        if part.startswith("+") or part == "joinchat":
            return text  # invite link — handled by import path
        return ("@" + part) if not part.lstrip("-").isdigit() else int(part)
    if text.lstrip("-").isdigit():
        return int(text)
    return text


async def _resolve_entity(account: dict, ref, join: bool):
    """Resolve (and optionally join) an entity via the account client."""
    client = await tg_client.get_client(account)
    if not client:
        return None
    try:
        ent = await client.get_entity(ref)
    except Exception as e:  # noqa: BLE001
        log.warning("resolve_entity failed for %r: %s", ref, e)
        return None
    if join:
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            await client(JoinChannelRequest(ent))
        except Exception as e:  # noqa: BLE001
            log.info("join failed/needless for %r: %s", ref, e)
    kind = "channel" if getattr(ent, "broadcast", False) else "chat"
    title = getattr(ent, "title", None) or getattr(ent, "username", None) or str(getattr(ent, "id", ref))
    return {"id": _peer_id(ent), "title": title, "kind": kind}


def _peer_id(ent) -> int:
    """Telethon entity → the -100… style id usable with the Bot side and storage."""
    cid = getattr(ent, "id", 0)
    if getattr(ent, "broadcast", False) or getattr(ent, "megagroup", False):
        return int(f"-100{cid}")
    return int(cid)


async def _render_list(update, context, aid: int, kind: str) -> None:
    lang = _lang(await get_user(update.effective_user.id))
    cfg = await get_config_for_agent(aid)
    items = await (get_sources if kind == "src" else get_targets)(cfg["config_id"])
    id_key = "source_id" if kind == "src" else "target_id"
    del_cb = "delsrc" if kind == "src" else "deltgt"
    listing = "\n".join(f"• {it.get('title') or it['chat_id']}" for it in items) or T(lang, "ap_empty")
    title = T(lang, "ap_src_title" if kind == "src" else "ap_tgt_title", list=listing)
    rows = [[InlineKeyboardButton(f"🗑 {it.get('title') or it['chat_id']}",
                                  callback_data=f"ap:{del_cb}:{it[id_key]}:{aid}")] for it in items]
    rows.append([InlineKeyboardButton(T(lang, "ap_add"),
                                      callback_data=f"ap:{'addsrc' if kind == 'src' else 'addtgt'}:{aid}")])
    rows.append([back_btn(f"ap:open:{aid}", lang), home_btn(lang)])
    await _show(update, context, title, InlineKeyboardMarkup(rows))


async def show_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await _render_list(update, context, int(update.callback_query.data.split(":")[2]), "src")


async def show_targets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await _render_list(update, context, int(update.callback_query.data.split(":")[2]), "tgt")


async def del_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, _, sid, aid = q.data.split(":")
    await remove_source(int(sid))
    await _render_list(update, context, int(aid), "src")


async def del_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, _, tid, aid = q.data.split(":")
    await remove_target(int(tid))
    await _render_list(update, context, int(aid), "tgt")


async def _add_start(update, context, aid: int, kind: str, state: int) -> int:
    q = update.callback_query
    user = await get_user(update.effective_user.id)
    lang = _lang(user)
    cfg = await get_config_for_agent(aid)
    # Must answer exactly once: a show_alert here is ignored if we already
    # answered earlier, so the "link an account first" notice never appeared.
    if not (cfg and cfg.get("account_id")):
        await q.answer(T(lang, "ap_need_account_first"), show_alert=True)
        return ConversationHandler.END
    await q.answer()
    context.user_data["ap_aid"] = aid
    context.user_data["ap_lang"] = lang
    context.user_data["ap_kind"] = kind
    await q.edit_message_text(
        T(lang, "ap_add_ask_src" if kind == "src" else "ap_add_ask_tgt"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[back_btn(
            f"ap:{'srcs' if kind == 'src' else 'tgts'}:{aid}", lang)]]))
    return state


async def add_source_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _add_start(update, context, int(update.callback_query.data.split(":")[2]), "src", AP_ADD_SOURCE)


async def add_target_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _add_start(update, context, int(update.callback_query.data.split(":")[2]), "tgt", AP_ADD_TARGET)


async def _add_got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("ap_lang", DEFAULT_LANG)
    aid = context.user_data.get("ap_aid")
    kind = context.user_data.get("ap_kind")
    cfg = await get_config_for_agent(aid)
    account = await get_account(cfg["account_id"]) if cfg and cfg.get("account_id") else None
    if not account:
        await update.message.reply_html(T(lang, "ap_need_account_first"))
        return ConversationHandler.END

    msg = update.message
    ref = None
    if msg.forward_origin is not None:
        origin = msg.forward_origin
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if chat is not None:
            ref = chat.username and ("@" + chat.username) or chat.id
    if ref is None and msg.text:
        ref = _parse_ref(msg.text)

    info = await _resolve_entity(account, ref, join=(kind == "src")) if ref is not None else None
    if not info:
        await update.message.reply_html(T(lang, "ap_resolve_fail"))
        return ConversationHandler.END

    if kind == "src":
        await add_source(cfg["config_id"], info["id"], info["title"], info["kind"])
    else:
        await add_target(cfg["config_id"], info["id"], info["title"])
    await update.message.reply_html(T(lang, "ap_added", title=info["title"]))
    await _render_list(update, context, aid, kind)
    return ConversationHandler.END


# ═══════════ settings ═══════════
async def _render_settings(update, context, aid: int) -> None:
    lang = _lang(await get_user(update.effective_user.id))
    cfg = await get_config_for_agent(aid)
    text = T(lang, "ap_set_title",
             interval=cfg.get("poll_interval"), jitter=cfg.get("jitter"),
             cap=cfg.get("max_per_window"), window=cfg.get("window_sec"),
             digest=cfg.get("digest_size"), editn=cfg.get("edit_last_n"))
    rows = [
        [InlineKeyboardButton(T(lang, "ap_set_interval", n=cfg.get("poll_interval")),
                              callback_data=f"ap:cyc:poll_interval:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_set_jitter", n=cfg.get("jitter")),
                              callback_data=f"ap:cyc:jitter:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_set_cap", n=cfg.get("max_per_window")),
                              callback_data=f"ap:cyc:max_per_window:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_set_window", n=cfg.get("window_sec")),
                              callback_data=f"ap:cyc:window_sec:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_set_digest", n=cfg.get("digest_size")),
                              callback_data=f"ap:cyc:digest_size:{aid}")],
        [InlineKeyboardButton(T(lang, "ap_set_editn", n=cfg.get("edit_last_n")),
                              callback_data=f"ap:cyc:edit_last_n:{aid}")],
        [back_btn(f"ap:open:{aid}", lang), home_btn(lang)],
    ]
    await _show(update, context, text, InlineKeyboardMarkup(rows))


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await _render_settings(update, context, int(update.callback_query.data.split(":")[2]))


async def cycle_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, _, field, aid = q.data.split(":")
    aid = int(aid)
    cfg = await get_config_for_agent(aid)
    if cfg and field in _STEPS:
        await update_config(cfg["config_id"], **{field: _cycle(field, cfg.get(field))})
    await _render_settings(update, context, aid)


# ═══════════ prompt + library ═══════════
async def _render_prompt(update, context, aid: int) -> None:
    import html as ihtml
    lang = _lang(await get_user(update.effective_user.id))
    cfg = await get_config_for_agent(aid)
    body = cfg.get("prompt") or ""
    disp = ihtml.escape(body[:600]) + ("…" if len(body) > 600 else "") if body else T(lang, "ap_prompt_empty")
    rows = [
        [InlineKeyboardButton(T(lang, "ap_prompt_edit"), callback_data=f"ap:pedit:{aid}"),
         InlineKeyboardButton(T(lang, "ap_prompt_lib"), callback_data=f"ap:plib:{aid}")],
        [back_btn(f"ap:open:{aid}", lang), home_btn(lang)],
    ]
    await _show(update, context, T(lang, "ap_prompt_title", body=disp), InlineKeyboardMarkup(rows))


async def show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await _render_prompt(update, context, int(update.callback_query.data.split(":")[2]))


async def prompt_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    lang = _lang(await get_user(q.from_user.id))
    context.user_data["ap_aid"] = aid
    context.user_data["ap_lang"] = lang
    await q.edit_message_text(T(lang, "ap_prompt_ask"), parse_mode=ParseMode.HTML,
                              reply_markup=InlineKeyboardMarkup([[back_btn(f"ap:prompt:{aid}", lang)]]))
    return AP_PROMPT


async def prompt_edit_got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    aid = context.user_data.get("ap_aid")
    cfg = await get_config_for_agent(aid)
    if cfg:
        await update_config(cfg["config_id"], prompt=(update.message.text or "").strip())
    await _render_prompt(update, context, aid)
    return ConversationHandler.END


async def _render_library(update, context, aid: int) -> None:
    uid = update.effective_user.id
    lang = _lang(await get_user(uid))
    presets = await get_autopost_presets(uid)
    rows = [[InlineKeyboardButton(f"📄 {p['name'] or p['preset_id']}",
                                  callback_data=f"ap:puse:{p['preset_id']}:{aid}"),
             InlineKeyboardButton("🗑", callback_data=f"ap:pdel:{p['preset_id']}:{aid}")]
            for p in presets]
    rows.append([InlineKeyboardButton(T(lang, "ap_lib_new"), callback_data=f"ap:pnew:{aid}")])
    rows.append([back_btn(f"ap:prompt:{aid}", lang), home_btn(lang)])
    body = T(lang, "ap_lib_title") if presets else (T(lang, "ap_lib_title") + "\n\n" + T(lang, "ap_lib_empty"))
    await _show(update, context, body, InlineKeyboardMarkup(rows))


async def show_library(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await _render_library(update, context, int(q.data.split(":")[2]))


async def library_use(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, _, pid, aid = q.data.split(":")
    preset = await get_autopost_preset(int(pid))
    cfg = await get_config_for_agent(int(aid))
    if preset and cfg:
        await update_config(cfg["config_id"], prompt=preset.get("body") or "")
    await _render_prompt(update, context, int(aid))


async def library_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, _, pid, aid = q.data.split(":")
    await delete_autopost_preset(int(pid))
    await _render_library(update, context, int(aid))


async def preset_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    lang = _lang(await get_user(q.from_user.id))
    context.user_data["ap_aid"] = aid
    context.user_data["ap_lang"] = lang
    await q.edit_message_text(T(lang, "ap_lib_new_ask"), parse_mode=ParseMode.HTML,
                              reply_markup=InlineKeyboardMarkup([[back_btn(f"ap:plib:{aid}", lang)]]))
    return AP_PRESET_NEW


async def preset_new_got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    aid = context.user_data.get("ap_aid")
    raw = (update.message.text or "").strip()
    name, _, body = raw.partition("\n")
    await create_autopost_preset(update.effective_user.id, name.strip()[:64], (body or name).strip())
    await _render_prompt(update, context, aid)
    return ConversationHandler.END


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


# ═══════════ registration ═══════════
def get_autopost_handlers() -> list:
    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_start, pattern=r"^ap:login:\d+$")],
        states={
            AP_API_ID: [CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$"),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_id)],
            AP_API_HASH: [CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$"),
                          MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_hash)],
            AP_PHONE: [CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$"),
                       MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            AP_CODE: [CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$"),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, login_code)],
            AP_2FA: [CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$"),
                     MessageHandler(filters.TEXT & ~filters.COMMAND, login_2fa)],
        },
        fallbacks=[CommandHandler("cancel", _cancel),
                   CallbackQueryHandler(login_cancel, pattern=r"^ap:acc:\d+$")],
        allow_reentry=True, per_message=False, name="ap_login", persistent=False,
    )
    add_source_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_source_start, pattern=r"^ap:addsrc:\d+$")],
        states={AP_ADD_SOURCE: [
            CallbackQueryHandler(show_sources, pattern=r"^ap:srcs:\d+$"),
            MessageHandler((filters.TEXT | filters.FORWARDED) & ~filters.COMMAND, _add_got)]},
        fallbacks=[CommandHandler("cancel", _cancel),
                   CallbackQueryHandler(show_sources, pattern=r"^ap:srcs:\d+$")],
        allow_reentry=True, per_message=False, name="ap_addsrc", persistent=False,
    )
    add_target_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_target_start, pattern=r"^ap:addtgt:\d+$")],
        states={AP_ADD_TARGET: [
            CallbackQueryHandler(show_targets, pattern=r"^ap:tgts:\d+$"),
            MessageHandler((filters.TEXT | filters.FORWARDED) & ~filters.COMMAND, _add_got)]},
        fallbacks=[CommandHandler("cancel", _cancel),
                   CallbackQueryHandler(show_targets, pattern=r"^ap:tgts:\d+$")],
        allow_reentry=True, per_message=False, name="ap_addtgt", persistent=False,
    )
    prompt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_edit_start, pattern=r"^ap:pedit:\d+$")],
        states={AP_PROMPT: [
            CallbackQueryHandler(show_prompt, pattern=r"^ap:prompt:\d+$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_edit_got)]},
        fallbacks=[CommandHandler("cancel", _cancel),
                   CallbackQueryHandler(show_prompt, pattern=r"^ap:prompt:\d+$")],
        allow_reentry=True, per_message=False, name="ap_prompt", persistent=False,
    )
    preset_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(preset_new_start, pattern=r"^ap:pnew:\d+$")],
        states={AP_PRESET_NEW: [
            CallbackQueryHandler(show_library, pattern=r"^ap:plib:\d+$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, preset_new_got)]},
        fallbacks=[CommandHandler("cancel", _cancel),
                   CallbackQueryHandler(show_library, pattern=r"^ap:plib:\d+$")],
        allow_reentry=True, per_message=False, name="ap_preset", persistent=False,
    )
    return [
        login_conv, add_source_conv, add_target_conv, prompt_conv, preset_conv,
        CallbackQueryHandler(open_config, pattern=r"^ap:open:\d+$"),
        CallbackQueryHandler(show_account, pattern=r"^ap:acc:\d+$"),
        CallbackQueryHandler(account_delete, pattern=r"^ap:accdel:\d+$"),
        CallbackQueryHandler(cycle_mode, pattern=r"^ap:mode:\d+$"),
        CallbackQueryHandler(toggle_enabled, pattern=r"^ap:toggle:\d+$"),
        CallbackQueryHandler(show_sources, pattern=r"^ap:srcs:\d+$"),
        CallbackQueryHandler(show_targets, pattern=r"^ap:tgts:\d+$"),
        CallbackQueryHandler(del_source, pattern=r"^ap:delsrc:\d+:\d+$"),
        CallbackQueryHandler(del_target, pattern=r"^ap:deltgt:\d+:\d+$"),
        CallbackQueryHandler(show_settings, pattern=r"^ap:set:\d+$"),
        CallbackQueryHandler(cycle_setting, pattern=r"^ap:cyc:[a-z_]+:\d+$"),
        CallbackQueryHandler(show_prompt, pattern=r"^ap:prompt:\d+$"),
        CallbackQueryHandler(show_library, pattern=r"^ap:plib:\d+$"),
        CallbackQueryHandler(library_use, pattern=r"^ap:puse:\d+:\d+$"),
        CallbackQueryHandler(library_del, pattern=r"^ap:pdel:\d+:\d+$"),
    ]
