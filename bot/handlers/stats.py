"""
Stats section: the user's own post-processing statistics, with an attached
16:9 chart (posts per day) and 1д/7д/30д period toggles.
"""
from __future__ import annotations

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from core.charts import render_daily_chart
from db.storage import get_user, get_user_detail_stats, posts_per_day
from handlers.menu import nav, nav_media
from keyboards.factory import stats_period_kb
from texts import t

_WINDOWS = (1, 7, 30)
_DEFAULT_WIN = 7


def _fmt_last(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "—"


def _window(update: Update) -> int:
    """Pull the period (days) from an `s:stats:<days>` callback, else the default."""
    q = update.callback_query
    if q and q.data and q.data.startswith("s:stats:"):
        try:
            win = int(q.data.split(":")[2])
            if win in _WINDOWS:
                return win
        except (ValueError, IndexError):
            pass
    return _DEFAULT_WIN


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    user = await get_user(uid)
    lang = (user or {}).get("lang") or "ru"
    win = _window(update)
    s = await get_user_detail_stats(uid)

    if not s.get("total"):
        text = f"{t(lang, 'stats_title')}\n\n{t(lang, 'stats_none')}"
        await nav(update, context, text, stats_period_kb(win, lang))
        return

    caption = t(
        lang, "stats_caption",
        processed=s["processed"], failed=s["failed"], rate=s["success_rate"],
        avg=s["avg_ms"], median=s["median_ms"],
        c24=s["c24"], c7=s["c7"], c30=s["c30"],
        channels=s["channels"], agents=s["agents"],
        first=_fmt_last(s["first_ts"]), last=_fmt_last(s["last_ts"]),
    )

    rows = await posts_per_day(uid, win)
    png = None
    try:
        png = render_daily_chart(
            rows,
            t(lang, "stats_chart_title"),
            subtitle=t(lang, "chart_sub_days", n=win),
            legend=(t(lang, "stats_legend_proc"), t(lang, "stats_legend_fail")),
        )
    except Exception:  # noqa: BLE001 — never let a render glitch break the screen
        png = None

    await nav_media(update, context, png, caption, stats_period_kb(win, lang))


def get_stats_handlers() -> list:
    return [
        CommandHandler("stats", show_stats),
        CallbackQueryHandler(show_stats, pattern=r"^menu:stats$"),
        CallbackQueryHandler(show_stats, pattern=r"^s:stats:\d+$"),
    ]
