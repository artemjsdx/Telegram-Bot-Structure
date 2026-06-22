"""
Admin panel: user list (search + paged) with rich per-user stat cards and
ban/unban, global stats with a new/left-users chart, broadcast (with confirm),
request logs, menu-banner management, bot description, a configurable support
contact, and an optional bot-channel line in the main menu.

Access is gated by ADMIN_IDS (config) or the per-user is_admin flag.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardMarkup, MessageOriginChannel
from telegram.constants import ParseMode
from telegram.error import Forbidden
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, filters,
)

from config import OWNER_ID
from constants import (
    T_BROADCAST, T_BANNER_MEDIA, T_DESC_LONG, T_DESC_SHORT,
    T_SUPPORT_ID, T_MENUCHAN_ID, T_MENUCHAN_LINK, T_USER_SEARCH,
    SET_BANNER_TYPE, SET_BANNER_FILE_ID,
    SET_BOT_DESCRIPTION, SET_BOT_SHORT_DESCRIPTION,
    BANNER_NONE, BANNER_PHOTO, BANNER_VIDEO,
    PAGE_SIZE_USERS, PAGE_SIZE_LOGS,
    SET_SUPPORT_ID, SET_MENU_CHANNEL_ENABLED, SET_MENU_CHANNEL_LINK,
    SET_MENU_CHANNEL_ID,
)
from db.storage import (
    get_user, list_users, count_users, set_banned, global_stats,
    recent_logs, get_setting, set_setting, delete_setting,
    set_blocked, get_user_detail_stats, posts_per_day, users_flow_per_day,
    search_users, count_search,
    active_channel_counts, channel_titles_for, get_channels_for_user,
)
from handlers.menu import nav, nav_media, is_admin
from keyboards.factory import (
    admin_menu_kb, admin_users_kb, admin_user_card_kb, admin_stats_kb,
    admin_support_kb, admin_menuchan_kb, admin_banner_kb, admin_desc_kb,
    confirm_kb, back_btn, home_btn,
)
from core.charts import render_daily_chart
from texts import t

log = logging.getLogger(__name__)

_DESC_LONG_MAX = 512
_DESC_SHORT_MAX = 120
_BANNER_LABELS = {BANNER_PHOTO: "📷 photo", BANNER_VIDEO: "🎬 video", BANNER_NONE: "—"}

_WINDOWS = (1, 7, 30)
_DEFAULT_WIN = 7

_TME_RE = re.compile(r"(?:https?://)?t\.me/(.+)$", re.IGNORECASE)


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


def _back_kb(cb: str, lang: str) -> InlineKeyboardMarkup:
    """Single Back button for an input-step prompt."""
    return InlineKeyboardMarkup([[back_btn(cb, lang)]])


def _fmt_ts(ts) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "—"


def _win_from(data: str, idx: int) -> int:
    """Read a period (days) from callback-data segment `idx`, clamped to _WINDOWS."""
    parts = (data or "").split(":")
    if len(parts) > idx and parts[idx].isdigit():
        win = int(parts[idx])
        if win in _WINDOWS:
            return win
    return _DEFAULT_WIN


# ───── menu / users / stats / logs ─────
async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    await _render(update, context, t(lang, "admin_title"), admin_menu_kb(lang), edit=False)


async def _with_chan_counts(users: list[dict]) -> list[dict]:
    """Attach the active bound-channel count to each user dict (for 📎/🖇️ markers)."""
    counts = await active_channel_counts([u["user_id"] for u in users])
    for u in users:
        u["chan_count"] = counts.get(u["user_id"], 0)
    return users


async def on_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    page = int(update.callback_query.data.split(":")[2])
    total = await count_users()
    users = await _with_chan_counts(
        await list_users(limit=PAGE_SIZE_USERS, offset=page * PAGE_SIZE_USERS))
    text = t(lang, "admin_users_title", count=total)
    await _render(update, context, text, admin_users_kb(users, page, total, lang))


def _display_name(s: dict) -> str:
    uname = s.get("username")
    if uname:
        return "@" + uname
    return s.get("first_name") or "—"


def _status_str(lang: str, s: dict) -> str:
    if s.get("is_banned"):
        return t(lang, "admin_user_status_banned")
    if s.get("blocked"):
        if s.get("block_kind") == "deleted":
            return t(lang, "admin_user_status_deleted")
        return t(lang, "admin_user_status_blocked")
    return t(lang, "admin_user_status_ok")


async def _resolve_channel(bot, channel_id: int, fallback_title: str) -> tuple[str, str | None, str | None]:
    """
    Best-effort (title, username, invite_link) for a channel via get_chat.
    A public channel exposes `username`; a private one may expose a primary
    `invite_link` if the bot is its admin. Either may be None; the title falls
    back to the stored one (which can be an emoji or empty).
    """
    title = (fallback_title or "").strip()
    username = invite = None
    try:
        chat = await bot.get_chat(channel_id)
        title = (chat.title or title or "").strip()
        username = chat.username
        if not username:
            invite = getattr(chat, "invite_link", None)
    except Exception:  # noqa: BLE001 — channel may be gone or the bot kicked
        pass
    return title, username, invite


async def _channels_block(bot, lang: str, tuid: int, budget: int) -> str:
    """
    HTML list of the user's active bound channels. Each line shows, separately,
    the name (if any), the link/@username (if any) and — always — the channel id
    (monospace, copyable). Lines are dropped whole to stay within `budget` chars,
    so the HTML caption is never sliced mid-tag.
    """
    chans = [c for c in await get_channels_for_user(tuid) if c.get("active")]
    if not chans:
        return t(lang, "admin_user_channels_none")
    lines, used, shown = [], 0, 0
    for c in chans:
        if shown >= 10:
            break
        cid = c["channel_id"]
        title, username, invite = await _resolve_channel(bot, cid, c.get("chan_title"))
        parts = []
        if title:
            if len(title) > 28:
                title = title[:27] + "…"
            parts.append(html.escape(title))
        if username:
            parts.append(f'<a href="https://t.me/{username}">@{username}</a>')
        elif invite:
            parts.append(f'<a href="{html.escape(invite, quote=True)}">{t(lang, "admin_user_channels_link")}</a>')
        parts.append(f"<code>{cid}</code>")
        line = "• " + " · ".join(parts)
        if lines and used + len(line) + 1 > budget:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1
    body = "\n".join(lines)
    if shown < len(chans):
        body += t(lang, "admin_user_channels_more", n=len(chans) - shown)
    return t(lang, "admin_user_channels", list=body)


async def _render_user_card(update, context, lang: str, tuid: int, win: int) -> None:
    s = await get_user_detail_stats(tuid)
    u = await get_user(tuid)
    if u is None and not s.get("total"):
        await _render(update, context, t(lang, "admin_user_none"), _nav_kb(lang))
        return
    caption = t(
        lang, "admin_user_card",
        name=html.escape(_display_name(s)), id=tuid, status=_status_str(lang, s),
        processed=s["processed"], failed=s["failed"], rate=s["success_rate"],
        avg=s["avg_ms"], median=s["median_ms"], max=s["max_ms"],
        c24=s["c24"], c7=s["c7"], c30=s["c30"],
        channels=s["channels"], agents=s["agents"],
        provider=html.escape(str(s["provider"])), ulang=s["lang"],
        created=_fmt_ts(s["created_at"]), last=_fmt_ts(s["last_ts"]),
    )
    # Budget the channels block by remaining caption room (Telegram cap is 1024);
    # reserve a margin for the block's header/“…more” wrapper text.
    caption += await _channels_block(context.bot, lang, tuid, budget=max(0, 1024 - len(caption) - 60))
    png = None
    try:
        png = render_daily_chart(
            await posts_per_day(tuid, win),
            t(lang, "stats_chart_title"),
            subtitle=t(lang, "chart_sub_days", n=win),
            legend=(t(lang, "stats_legend_proc"), t(lang, "stats_legend_fail")),
        )
    except Exception:  # noqa: BLE001 — a render glitch must never break the card
        png = None
    await nav_media(update, context, png, caption,
                    admin_user_card_kb(tuid, s["is_banned"], win, lang))


async def on_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    data = update.callback_query.data
    tuid = int(data.split(":")[2])
    await _render_user_card(update, context, lang, tuid, _win_from(data, 3))


async def on_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    tuid = int(update.callback_query.data.split(":")[2])
    await set_banned(tuid, True)
    await update.callback_query.answer(t(lang, "admin_user_banned"))
    await _render_user_card(update, context, lang, tuid, _DEFAULT_WIN)


async def on_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    tuid = int(update.callback_query.data.split(":")[2])
    await set_banned(tuid, False)
    await update.callback_query.answer(t(lang, "admin_user_unbanned"))
    await _render_user_card(update, context, lang, tuid, _DEFAULT_WIN)


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    win = _win_from(update.callback_query.data, 2)
    g = await global_stats()
    active = max(0, g["users"] - g["blocked"] - g["deleted"] - g["banned"])
    caption = t(
        lang, "admin_gstats",
        users=g["users"], active=active, blocked=g["blocked"],
        deleted=g["deleted"], banned=g["banned"],
        processed=g["processed"], failed=g["failed"],
    )
    png = None
    try:
        png = render_daily_chart(
            await users_flow_per_day(win),
            t(lang, "admin_gstats_chart_title"),
            subtitle=t(lang, "chart_sub_days", n=win),
            legend=(t(lang, "admin_gstats_legend_join"), t(lang, "admin_gstats_legend_left")),
        )
    except Exception:  # noqa: BLE001
        png = None
    await nav_media(update, context, png, caption, admin_stats_kb(win, lang))


async def on_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    logs = await recent_logs(PAGE_SIZE_LOGS)
    if not logs:
        body = t(lang, "admin_logs_empty")
    else:
        titles = await channel_titles_for([e.get("channel_id") for e in logs])
        lines = []
        for entry in logs:
            mark = "✅" if entry.get("ok") else "❌"
            when = datetime.fromtimestamp(entry.get("ts") or 0, tz=timezone.utc).strftime("%m-%d %H:%M")
            prov = html.escape(str(entry.get("provider") or "—"))
            model = html.escape(str(entry.get("model") or "—"))
            lines.append(f"{mark} <code>{when}</code> {prov}/{model} · {entry.get('response_ms', 0)}ms")
            cid = entry.get("channel_id")
            if cid:
                chan = titles.get(cid) or f"id {cid}"
                if len(chan) > 32:
                    chan = chan[:31] + "…"
                lines.append(f"   📣 {html.escape(chan)}")
            if not entry.get("ok") and entry.get("error"):
                lines.append(f"   <i>{html.escape(str(entry['error'])[:80])}</i>")
        body = "\n".join(lines)
    await _render(update, context, t(lang, "admin_logs_title") + "\n\n" + body, _nav_kb(lang))


# ───── user search (conversation) ─────
async def ask_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        t(lang, "admin_user_search_prompt"),
        reply_markup=_back_kb("admin:users:0", lang),
    )
    return T_USER_SEARCH


async def got_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    query = (update.message.text or "").strip()
    if not query:
        return T_USER_SEARCH
    context.user_data["user_search"] = query
    total = await count_search(query)
    if not total:
        await update.message.reply_html(
            t(lang, "admin_user_search_none", q=html.escape(query)),
            reply_markup=_back_kb("admin:users:0", lang),
        )
        return ConversationHandler.END
    users = await _with_chan_counts(
        await search_users(query, limit=PAGE_SIZE_USERS, offset=0))
    text = t(lang, "admin_user_search_title", q=html.escape(query), count=total)
    kb = admin_users_kb(users, 0, total, lang,
                        page_prefix="admin:usearch:pg", show_search=False,
                        back_cb="admin:users:0")
    await update.message.reply_html(text, reply_markup=kb, disable_web_page_preview=True)
    return ConversationHandler.END


async def on_user_search_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    page = int(update.callback_query.data.split(":")[3])
    query = context.user_data.get("user_search", "")
    total = await count_search(query)
    users = await _with_chan_counts(
        await search_users(query, limit=PAGE_SIZE_USERS, offset=page * PAGE_SIZE_USERS))
    text = t(lang, "admin_user_search_title", q=html.escape(query), count=total)
    kb = admin_users_kb(users, page, total, lang,
                        page_prefix="admin:usearch:pg", show_search=False,
                        back_cb="admin:users:0")
    await _render(update, context, text, kb)


# ───── support contact ─────
async def _resolve_handle(bot, uid: int) -> str:
    """Best-effort @username (or escaped display name / id) for a contact."""
    try:
        chat = await bot.get_chat(uid)
        if chat.username:
            return f"@{chat.username}"
        return html.escape(chat.full_name or str(uid))
    except Exception:  # noqa: BLE001
        return str(uid)


async def _support_id() -> int:
    raw = await get_setting(SET_SUPPORT_ID)
    try:
        return int(raw) if raw else OWNER_ID
    except (TypeError, ValueError):
        return OWNER_ID


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    sid = await _support_id()
    handle = await _resolve_handle(context.bot, sid)
    text = t(lang, "admin_support_title", handle=handle, id=sid)
    await _render(update, context, text, admin_support_kb(lang))


async def ask_support_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        t(lang, "admin_support_prompt"),
        reply_markup=_back_kb("admin:support", lang),
    )
    return T_SUPPORT_ID


async def got_support_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    raw = (update.message.text or "").strip().lstrip("@")
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text(
            t(lang, "admin_support_bad"), reply_markup=_back_kb("admin:support", lang))
        return T_SUPPORT_ID
    sid = int(raw)
    await set_setting(SET_SUPPORT_ID, str(sid))
    handle = await _resolve_handle(context.bot, sid)
    await update.message.reply_html(
        t(lang, "admin_support_title", handle=handle, id=sid),
        reply_markup=admin_support_kb(lang), disable_web_page_preview=True,
    )
    return ConversationHandler.END


# ───── bot-channel line in the main menu ─────
async def _menuchan_payload(lang: str):
    enabled = (await get_setting(SET_MENU_CHANNEL_ENABLED)) == "1"
    link = await get_setting(SET_MENU_CHANNEL_LINK)
    configured = bool(link)
    status = t(lang, "admin_menuchan_on" if enabled else "admin_menuchan_off")
    link_disp = html.escape(link) if link else t(lang, "admin_menuchan_none")
    text = t(lang, "admin_menuchan_title", status=status, link=link_disp)
    return text, admin_menuchan_kb(enabled, configured, lang)


async def show_menuchan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    text, kb = await _menuchan_payload(lang)
    await _render(update, context, text, kb)


async def _resolve_username(uname: str, bot) -> dict:
    """Build link/title for a public @username, validating via get_chat best-effort."""
    uname = uname.strip().lstrip("@")
    info = {"id": None, "username": uname, "title": "@" + uname, "link": f"https://t.me/{uname}"}
    try:
        chat = await bot.get_chat("@" + uname)
        info["id"] = chat.id
        info["title"] = chat.title or info["title"]
        if chat.username:
            info["link"] = f"https://t.me/{chat.username}"
    except Exception:  # noqa: BLE001 — link is still usable without validation
        pass
    return info


async def _resolve_menuchan(msg, bot) -> dict | None:
    """
    Resolve a channel from a forwarded post or text (@username / t.me link / -100… id).
    Returns {id, username, title, link}; link is None for a private channel (needs a
    manual invite link). Returns None when nothing could be recognized.
    """
    fwd = getattr(msg, "forward_origin", None)
    if isinstance(fwd, MessageOriginChannel):
        chat = fwd.chat
        uname = chat.username
        return {
            "id": chat.id, "username": uname,
            "title": chat.title or (("@" + uname) if uname else str(chat.id)),
            "link": f"https://t.me/{uname}" if uname else None,
        }

    txt = (getattr(msg, "text", "") or "").strip()
    if not txt:
        return None
    low = txt.lower()

    # Private invite link → use verbatim.
    if "t.me/+" in low or "joinchat/" in low:
        link = txt if low.startswith("http") else "https://" + txt.lstrip("/")
        return {"id": None, "username": None, "title": "", "link": link}

    # Public t.me/<username> link.
    m = _TME_RE.match(txt)
    if m:
        rest = m.group(1).strip("/").split("/")[0].split("?")[0]
        if rest and not rest.startswith("+"):
            return await _resolve_username(rest, bot)

    if txt.startswith("@"):
        return await _resolve_username(txt, bot)

    # Numeric channel id (-100…): only get_chat can tell public from private.
    if txt.lstrip("-").isdigit():
        try:
            chat = await bot.get_chat(int(txt))
        except Exception:  # noqa: BLE001
            return None
        uname = chat.username
        return {
            "id": chat.id, "username": uname,
            "title": chat.title or (("@" + uname) if uname else str(chat.id)),
            "link": f"https://t.me/{uname}" if uname else None,
        }

    # Bare username without @.
    if re.fullmatch(r"[A-Za-z0-9_]{4,32}", txt):
        return await _resolve_username(txt, bot)

    return None


async def ask_menuchan_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        t(lang, "admin_menuchan_ask_id"), parse_mode=ParseMode.HTML,
        reply_markup=_back_kb("admin:menuchan", lang),
    )
    return T_MENUCHAN_ID


async def back_menuchan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back button inside the setup flow → return to the status screen, end conv."""
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    text, kb = await _menuchan_payload(lang)
    try:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        await nav(update, context, text, kb)
    return ConversationHandler.END


async def got_menuchan_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    msg = update.message
    info = await _resolve_menuchan(msg, context.bot)
    if info is None:
        await msg.reply_html(
            t(lang, "admin_menuchan_bad_id"), reply_markup=_back_kb("admin:menuchan", lang))
        return T_MENUCHAN_ID

    if info["link"]:
        await set_setting(SET_MENU_CHANNEL_LINK, info["link"])
        if info["id"]:
            await set_setting(SET_MENU_CHANNEL_ID, str(info["id"]))
        await set_setting(SET_MENU_CHANNEL_ENABLED, "1")
        context.user_data.pop("menuchan_id", None)
        text, kb = await _menuchan_payload(lang)
        await msg.reply_html(t(lang, "admin_menuchan_saved"))
        await msg.reply_html(text, reply_markup=kb, disable_web_page_preview=True)
        return ConversationHandler.END

    # Private channel → ask for a manual invite link.
    context.user_data["menuchan_id"] = info["id"]
    await msg.reply_html(
        t(lang, "admin_menuchan_ask_link"),
        reply_markup=_back_kb("admin:menuchan:setup", lang),
    )
    return T_MENUCHAN_LINK


def _valid_link(s: str) -> bool:
    low = (s or "").strip().lower()
    return low.startswith("http://") or low.startswith("https://") or low.startswith("t.me/")


async def got_menuchan_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, lang = await _guard(update)
    if user is None:
        return ConversationHandler.END
    msg = update.message
    link = (msg.text or "").strip()
    if not _valid_link(link):
        await msg.reply_html(
            t(lang, "admin_menuchan_bad_link"),
            reply_markup=_back_kb("admin:menuchan:setup", lang))
        return T_MENUCHAN_LINK
    if not link.lower().startswith("http"):
        link = "https://" + link.lstrip("/")
    await set_setting(SET_MENU_CHANNEL_LINK, link)
    cid = context.user_data.pop("menuchan_id", None)
    if cid:
        await set_setting(SET_MENU_CHANNEL_ID, str(cid))
    await set_setting(SET_MENU_CHANNEL_ENABLED, "1")
    text, kb = await _menuchan_payload(lang)
    await msg.reply_html(t(lang, "admin_menuchan_saved"))
    await msg.reply_html(text, reply_markup=kb, disable_web_page_preview=True)
    return ConversationHandler.END


async def on_menuchan_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    if not await get_setting(SET_MENU_CHANNEL_LINK):
        await update.callback_query.answer(t(lang, "admin_menuchan_none"), show_alert=True)
        return
    now_on = (await get_setting(SET_MENU_CHANNEL_ENABLED)) == "1"
    await set_setting(SET_MENU_CHANNEL_ENABLED, "0" if now_on else "1")
    await update.callback_query.answer(
        t(lang, "admin_menuchan_toggled_off" if now_on else "admin_menuchan_toggled_on"))
    await show_menuchan(update, context)


async def on_menuchan_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    await delete_setting(SET_MENU_CHANNEL_ENABLED)
    await delete_setting(SET_MENU_CHANNEL_LINK)
    await delete_setting(SET_MENU_CHANNEL_ID)
    await update.callback_query.answer(t(lang, "admin_menuchan_cleared"))
    await show_menuchan(update, context)


# ───── leave/return tracking (user blocks or restarts the bot) ─────
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cm = update.my_chat_member
    if cm is None or cm.chat.type != "private":
        return
    status = cm.new_chat_member.status
    if status in ("kicked", "left"):
        # "kicked" = the user blocked the bot; "left" we record under the same
        # umbrella. Telegram has no event for "deleted the chat without blocking".
        await set_blocked(cm.chat.id, True, kind="blocked")
    elif status == "member":
        await set_blocked(cm.chat.id, False)


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
    msg = update.message
    if not (msg.text or "").strip():
        return T_BROADCAST
    # Keep the admin's formatting ("fonts") by carrying the raw text plus its
    # entities; entities survive the broadcast verbatim, including custom emoji.
    context.user_data["broadcast_text"] = msg.text
    context.user_data["broadcast_entities"] = msg.entities
    await msg.reply_html(
        f"📢\n\n{msg.text_html}",
        reply_markup=confirm_kb("admin:bc_yes", "menu:admin", lang),
    )
    return ConversationHandler.END


def _block_kind_from_error(exc) -> str:
    """Classify a Forbidden/send error into 'deleted' (account gone) vs 'blocked'."""
    msg = str(getattr(exc, "message", "") or exc).lower()
    if "deactiv" in msg or "not found" in msg or "can't initiate" in msg:
        return "deleted"
    return "blocked"


async def on_broadcast_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, lang = await _guard(update)
    if user is None:
        return
    text = context.user_data.pop("broadcast_text", "")
    entities = context.user_data.pop("broadcast_entities", None)
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
            await context.bot.send_message(u["user_id"], text, entities=entities)
            ok += 1
        except Forbidden as exc:
            # Forbidden tells us *why* the user is unreachable: a deactivated
            # account is the closest thing Telegram has to "deleted the bot",
            # everything else is a plain block.
            await set_blocked(u["user_id"], True, kind=_block_kind_from_error(exc))
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
    context.user_data.pop("menuchan_id", None)
    return ConversationHandler.END


def get_admin_handlers() -> list:
    input_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_broadcast, pattern=r"^admin:broadcast$"),
            CallbackQueryHandler(ask_banner_photo, pattern=r"^admin:banner:photo$"),
            CallbackQueryHandler(ask_banner_video, pattern=r"^admin:banner:video$"),
            CallbackQueryHandler(ask_desc_long, pattern=r"^admin:desc:long$"),
            CallbackQueryHandler(ask_desc_short, pattern=r"^admin:desc:short$"),
            CallbackQueryHandler(ask_support_id, pattern=r"^admin:support:set$"),
            CallbackQueryHandler(ask_menuchan_setup, pattern=r"^admin:menuchan:setup$"),
            CallbackQueryHandler(ask_user_search, pattern=r"^admin:usearch$"),
        ],
        states={
            T_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_broadcast)],
            T_BANNER_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, got_banner_media)],
            T_DESC_LONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc_long)],
            T_DESC_SHORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc_short)],
            T_SUPPORT_ID: [
                CallbackQueryHandler(show_support, pattern=r"^admin:support$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_support_id),
            ],
            T_MENUCHAN_ID: [
                CallbackQueryHandler(back_menuchan, pattern=r"^admin:menuchan$"),
                MessageHandler(filters.FORWARDED | (filters.TEXT & ~filters.COMMAND), got_menuchan_id),
            ],
            T_MENUCHAN_LINK: [
                CallbackQueryHandler(ask_menuchan_setup, pattern=r"^admin:menuchan:setup$"),
                CallbackQueryHandler(back_menuchan, pattern=r"^admin:menuchan$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_menuchan_link),
            ],
            T_USER_SEARCH: [
                CallbackQueryHandler(on_users, pattern=r"^admin:users:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_user_search),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern=r"^menu:"),
            CommandHandler("cancel", cancel),
        ],
        # Reentry lets an admin re-press an input button to restart a flow even if
        # a previous wait was left dangling (e.g. they sent /start instead of the
        # expected value) — without it the entry point stays inert. It also powers
        # the "back to previous step" buttons in the menu-channel setup.
        allow_reentry=True,
        per_message=False,
        name="admin_input",
        persistent=False,
    )
    return [
        input_conv,
        CommandHandler("admin", show_admin),
        ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER),
        CallbackQueryHandler(show_admin, pattern=r"^menu:admin$"),
        CallbackQueryHandler(on_users, pattern=r"^admin:users:\d+$"),
        CallbackQueryHandler(on_user_search_page, pattern=r"^admin:usearch:pg:\d+$"),
        CallbackQueryHandler(on_user, pattern=r"^admin:user:\d+(?::\d+)?$"),
        CallbackQueryHandler(on_ban, pattern=r"^admin:ban:\d+$"),
        CallbackQueryHandler(on_unban, pattern=r"^admin:unban:\d+$"),
        CallbackQueryHandler(on_stats, pattern=r"^admin:stats(?::\d+)?$"),
        CallbackQueryHandler(on_logs, pattern=r"^admin:logs$"),
        CallbackQueryHandler(on_broadcast_yes, pattern=r"^admin:bc_yes$"),
        CallbackQueryHandler(on_banner_remove, pattern=r"^admin:banner:remove$"),
        CallbackQueryHandler(show_banner, pattern=r"^admin:banner$"),
        CallbackQueryHandler(show_desc, pattern=r"^admin:desc$"),
        CallbackQueryHandler(show_support, pattern=r"^admin:support$"),
        CallbackQueryHandler(on_menuchan_toggle, pattern=r"^admin:menuchan:toggle$"),
        CallbackQueryHandler(on_menuchan_clear, pattern=r"^admin:menuchan:clear$"),
        CallbackQueryHandler(show_menuchan, pattern=r"^admin:menuchan$"),
    ]
