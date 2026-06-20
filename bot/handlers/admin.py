"""
Admin panel: user list + ban/unban, global stats, broadcast (with confirm),
request logs, menu-banner management (photo/video upload → file_id), and bot
description editing (long/short, pushed to Telegram via the Bot API).

Access is gated by ADMIN_IDS (config) or the per-user is_admin flag.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from constants import (
    T_BROADCAST, T_BANNER_MEDIA, T_DESC_LONG, T_DESC_SHORT,
    SET_BANNER_TYPE, SET_BANNER_FILE_ID,
    SET_BOT_DESCRIPTION, SET_BOT_SHORT_DESCRIPTION,
    BANNER_NONE, BANNER_PHOTO, BANNER_VIDEO,
    PAGE_SIZE_USERS, PAGE_SIZE_LOGS,
)
from db.storage import (
    get_user, list_users, count_users, set_banned, global_stats,
    recent_logs, get_setting, set_setting, delete_setting,
)
from handlers.menu import nav, is_admin
from keyboards.factory import (
    admin_menu_kb, admin_users_kb, admin_user_actions_kb,
    admin_banner_kb, admin_desc_kb, confirm_kb, back_btn, home_btn,
)
from texts import t

log = logging.getLogger(__name__)

_DESC_LONG_MAX = 512
_DESC_SHORT_MAX = 120
_BANNER_LABELS = {BANNER_PHOTO: "📷 photo", BANNER_VIDEO: "🎬 video", BANNER_NONE: "—"}


# ───── helpers ─────
async def _guard(update: Update):
    """Return ({user}, lang) for admins, (None, lang) otherwise (after denying)."""
    uid = update.effective_user.id
    user = await get_user(uid)
    lang = (user or {}).get("lang") or "ru"
    if not is_admin(user, uid):
        q = update.callback_query
        if q:
            await q.answer(t(lang, "admin_only"), show_alert=True)
        elif update.message:
            await update.message.reply_text(t(lang, "admin_only"))
        return None, lang
    return (user or {}), lang


async def _render(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb, edit: bool = True) -> None:
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=kb,
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


def _nav_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[back_btn("menu:admin", lang), home_btn(lang)]])


# ───── menu / users / stats / logs ─────
async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    await _render(update, context, t(lang, "admin_title"), admin_menu_kb(lang), edit=False)


async def on_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    page = int(update.callback_query.data.split(":")[2])
    total = await count_users()
    users = await list_users(limit=PAGE_SIZE_USERS, offset=page * PAGE_SIZE_USERS)
    text = t(lang, "admin_users_title", count=total)
    await _render(update, context, text, admin_users_kb(users, page, total, lang))


def _user_detail(tuid: int, u: dict | None, banned: bool) -> str:
    return (
        f"👤 <code>{tuid}</code>\n"
        f"{'🚫' if banned else '✅'}  🌐 {(u or {}).get('lang', '—')}  "
        f"🔌 {(u or {}).get('provider', '—')}\n"
        f"📊 {(u or {}).get('posts_processed', 0)}  ·  "
        f"❌ {(u or {}).get('posts_failed', 0)}"
    )


async def _render_user(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str, tuid: int) -> None:
    u = await get_user(tuid)
    banned = bool(u and u.get("is_banned"))
    await _render(update, context, _user_detail(tuid, u, banned),
                  admin_user_actions_kb(tuid, banned, lang))


async def on_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    await update.callback_query.answer()
    tuid = int(update.callback_query.data.split(":")[2])
    await _render_user(update, context, lang, tuid)


async def on_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    tuid = int(update.callback_query.data.split(":")[2])
    await set_banned(tuid, True)
    await update.callback_query.answer(t(lang, "admin_user_banned"))
    await _render_user(update, context, lang, tuid)


async def on_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    tuid = int(update.callback_query.data.split(":")[2])
    await set_banned(tuid, False)
    await update.callback_query.answer(t(lang, "admin_user_unbanned"))
    await _render_user(update, context, lang, tuid)


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    g = await global_stats()
    text = t(lang, "admin_gstats", users=g["users"], processed=g["processed"], failed=g["failed"])
    await _render(update, context, text, _nav_kb(lang))


async def on_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    logs = await recent_logs(PAGE_SIZE_LOGS)
    if not logs:
        body = t(lang, "admin_logs_empty")
    else:
        lines = []
        for entry in logs:
            mark = "✅" if entry.get("ok") else "❌"
            when = datetime.fromtimestamp(entry.get("ts") or 0, tz=timezone.utc).strftime("%m-%d %H:%M")
            prov = html.escape(str(entry.get("provider") or "—"))
            model = html.escape(str(entry.get("model") or "—"))
            lines.append(f"{mark} <code>{when}</code> {prov}/{model} · {entry.get('response_ms', 0)}ms")
            if not entry.get("ok") and entry.get("error"):
                lines.append(f"   <i>{html.escape(str(entry['error'])[:80])}</i>")
        body = "\n".join(lines)
    await _render(update, context, t(lang, "admin_logs_title") + "\n\n" + body, _nav_kb(lang))


# ───── banner: status + remove (immediate) ─────
async def show_banner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    current = await get_setting(SET_BANNER_TYPE) or BANNER_NONE
    text = t(lang, "admin_banner_title", current=_BANNER_LABELS.get(current, current))
    await _render(update, context, text, admin_banner_kb(current, lang))


async def on_banner_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    await set_setting(SET_BANNER_TYPE, BANNER_NONE)
    await delete_setting(SET_BANNER_FILE_ID)
    await update.callback_query.answer(t(lang, "admin_banner_removed"))
    await show_banner(update, context)


# ───── description: status (immediate) ─────
async def show_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    long = await get_setting(SET_BOT_DESCRIPTION) or t(lang, "bot_desc_long")
    short = await get_setting(SET_BOT_SHORT_DESCRIPTION) or t(lang, "bot_desc_short")
    text = t(lang, "admin_desc_title", long=html.escape(long), short=html.escape(short))
    await _render(update, context, text, admin_desc_kb(lang))


# ───── broadcast (conversation + confirm) ─────
async def ask_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(t(lang, "admin_broadcast_prompt"))
    return T_BROADCAST


async def got_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        return T_BROADCAST
    context.user_data["broadcast_text"] = text
    await update.message.reply_html(
        f"📢\n\n{html.escape(text)}",
        reply_markup=confirm_kb("admin:bc_yes", "menu:admin", lang),
    )
    return ConversationHandler.END


async def on_broadcast_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    text = context.user_data.pop("broadcast_text", "")
    q = update.callback_query
    if not text:
        await q.answer()
        await show_admin(update, context)
        return
    await q.answer()
    total = await count_users()
    recipients = await list_users(limit=total or 1, offset=0)
    ok = 0
    for u in recipients:
        if u.get("is_banned"):
            continue
        try:
            await context.bot.send_message(u["user_id"], text)
            ok += 1
        except Exception:
            pass
    await nav(update, context, t(lang, "admin_broadcast_sent", ok=ok, total=total), admin_menu_kb(lang))


# ───── banner upload (conversation) ─────
async def ask_banner_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    context.user_data["banner_kind"] = BANNER_PHOTO
    await update.callback_query.edit_message_text(t(lang, "admin_banner_send_photo"))
    return T_BANNER_MEDIA


async def ask_banner_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    context.user_data["banner_kind"] = BANNER_VIDEO
    await update.callback_query.edit_message_text(t(lang, "admin_banner_send_video"))
    return T_BANNER_MEDIA


async def got_banner_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    kind = context.user_data.get("banner_kind", BANNER_PHOTO)
    msg = update.message
    file_id = None
    if kind == BANNER_PHOTO and msg.photo:
        file_id = msg.photo[-1].file_id
    elif kind == BANNER_VIDEO and msg.video:
        file_id = msg.video.file_id

    if not file_id:
        await msg.reply_text(t(lang, "admin_banner_wrong", kind=_BANNER_LABELS.get(kind, kind)))
        return T_BANNER_MEDIA

    await set_setting(SET_BANNER_TYPE, kind)
    await set_setting(SET_BANNER_FILE_ID, file_id)
    context.user_data.pop("banner_kind", None)
    await msg.reply_text(t(lang, "admin_banner_saved"))
    current = kind
    await nav(update, context,
              t(lang, "admin_banner_title", current=_BANNER_LABELS.get(current, current)),
              admin_banner_kb(current, lang))
    return ConversationHandler.END


# ───── description edit (conversation) ─────
async def ask_desc_long(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(t(lang, "admin_desc_enter_long"))
    return T_DESC_LONG


async def ask_desc_short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(t(lang, "admin_desc_enter_short"))
    return T_DESC_SHORT


async def got_desc_long(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    text = (update.message.text or "").strip()[:_DESC_LONG_MAX]
    await set_setting(SET_BOT_DESCRIPTION, text)
    try:
        await context.bot.set_my_description(description=text)
    except Exception as e:
        log.warning("set_my_description failed: %s", e)
    await update.message.reply_text(t(lang, "admin_desc_saved"))
    await show_desc(update, context)
    return ConversationHandler.END


async def got_desc_short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    text = (update.message.text or "").strip()[:_DESC_SHORT_MAX]
    await set_setting(SET_BOT_SHORT_DESCRIPTION, text)
    try:
        await context.bot.set_my_short_description(short_description=text)
    except Exception as e:
        log.warning("set_my_short_description failed: %s", e)
    await update.message.reply_text(t(lang, "admin_desc_saved"))
    await show_desc(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("banner_kind", None)
    context.user_data.pop("broadcast_text", None)
    return ConversationHandler.END


def get_admin_handlers() -> list:
    input_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_broadcast, pattern=r"^admin:broadcast$"),
            CallbackQueryHandler(ask_banner_photo, pattern=r"^admin:banner:photo$"),
            CallbackQueryHandler(ask_banner_video, pattern=r"^admin:banner:video$"),
            CallbackQueryHandler(ask_desc_long, pattern=r"^admin:desc:long$"),
            CallbackQueryHandler(ask_desc_short, pattern=r"^admin:desc:short$"),
        ],
        states={
            T_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_broadcast)],
            T_BANNER_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, got_banner_media)],
            T_DESC_LONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc_long)],
            T_DESC_SHORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc_short)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern=r"^menu:"),
            CommandHandler("cancel", cancel),
        ],
        per_message=False,
        name="admin_input",
        persistent=False,
    )
    return [
        input_conv,
        CommandHandler("admin", show_admin),
        CallbackQueryHandler(show_admin, pattern=r"^menu:admin$"),
        CallbackQueryHandler(on_users, pattern=r"^admin:users:\d+$"),
        CallbackQueryHandler(on_user, pattern=r"^admin:user:\d+$"),
        CallbackQueryHandler(on_ban, pattern=r"^admin:ban:\d+$"),
        CallbackQueryHandler(on_unban, pattern=r"^admin:unban:\d+$"),
        CallbackQueryHandler(on_stats, pattern=r"^admin:stats$"),
        CallbackQueryHandler(on_logs, pattern=r"^admin:logs$"),
        CallbackQueryHandler(on_broadcast_yes, pattern=r"^admin:bc_yes$"),
        CallbackQueryHandler(on_banner_remove, pattern=r"^admin:banner:remove$"),
        CallbackQueryHandler(show_banner, pattern=r"^admin:banner$"),
        CallbackQueryHandler(show_desc, pattern=r"^admin:desc$"),
    ]
