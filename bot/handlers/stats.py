"""
Stats section: show the user's aggregated post-processing statistics.
"""
from __future__ import annotations

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from db.storage import get_user, get_stats_for_user
from handlers.menu import nav
from keyboards.factory import home_btn
from texts import t

from telegram import InlineKeyboardMarkup


def _fmt_last(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "—"


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    user = await get_user(uid)
    lang = (user or {}).get("lang") or "ru"
    stats = await get_stats_for_user(uid)

    if not stats.get("total"):
        text = f"{t(lang, 'stats_title')}\n\n{t(lang, 'stats_none')}"
    else:
        text = t(lang, "stats_title") + "\n\n" + t(
            lang, "stats_body",
            processed=stats["total"],
            failed=stats["failed"],
            avg_ms=stats["avg_ms"],
            last=_fmt_last(stats["last_ts"]),
        )

    kb = InlineKeyboardMarkup([[home_btn(lang)]])
    await nav(update, context, text, kb)


def get_stats_handlers() -> list:
    return [
        CommandHandler("stats", show_stats),
        CallbackQueryHandler(show_stats, pattern=r"^menu:stats$"),
    ]
