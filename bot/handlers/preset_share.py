"""
Recipient side of preset sharing.

These handlers live OUTSIDE any conversation (registered globally, group 0)
because the offer message arrives unsolicited — the recipient may have no active
dialog. Every action re-checks that the caller owns the offer and that it is
still pending, so stale taps (after the offer was handled) and forged share_ids
belonging to someone else are rejected.
"""
from __future__ import annotations

import html
import logging

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from config import DEFAULT_LANG
from db.storage import (
    get_user, get_preset_share, set_preset_share_status,
    get_agents_for_user, get_agent, update_agent, create_user_preset,
)
from keyboards.factory import (
    pshare_offer_kb, pshare_view_kb, pshare_pick_agent_kb, home_btn,
)
from texts import t

log = logging.getLogger(__name__)


def _who(u: dict | None) -> str:
    """A readable handle for a user: @username → name → numeric id."""
    if not u:
        return "?"
    if u.get("username"):
        return "@" + u["username"]
    if u.get("first_name"):
        return html.escape(u["first_name"])
    return str(u.get("user_id"))


def _home_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[home_btn(lang)]])


async def _lang_of(uid: int) -> str:
    u = await get_user(uid)
    return (u or {}).get("lang") or DEFAULT_LANG


async def _load(update: Update):
    """
    Return (share, lang) if the caller may act on a pending offer, else
    (None, lang). On rejection, answers with a stale toast and drops the dead
    keyboard so the buttons can't be tapped again.
    """
    q = update.callback_query
    lang = await _lang_of(q.from_user.id)
    sid = int(q.data.split(":")[2])
    share = await get_preset_share(sid)
    if not share or share["to_user"] != q.from_user.id or share["status"] != "pending":
        await q.answer(t(lang, "pshare_stale"), show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 — message may be old/uneditable
            pass
        return None, lang
    return share, lang


async def on_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    await q.answer()
    sender = await get_user(share["from_user"])
    body = html.escape(share["body"])
    if len(body) > 3500:
        body = body[:3500] + "…"
    await q.edit_message_text(
        t(lang, "pshare_body", name=html.escape(share["name"]), sender=_who(sender), body=body),
        parse_mode=ParseMode.HTML, reply_markup=pshare_view_kb(share["share_id"], lang),
    )


async def on_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    await q.answer()
    sender = await get_user(share["from_user"])
    await q.edit_message_text(
        t(lang, "preset_share_recv", sender=_who(sender), name=html.escape(share["name"])),
        parse_mode=ParseMode.HTML, reply_markup=pshare_offer_kb(share["share_id"], lang),
    )


async def on_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    agents = await get_agents_for_user(q.from_user.id)
    if not agents:
        # Nothing to apply to — stash it in the library instead and close out.
        await create_user_preset(q.from_user.id, share["name"], share["body"])
        await set_preset_share_status(share["share_id"], "accepted")
        await q.answer()
        await q.edit_message_text(
            t(lang, "pshare_no_agents", name=html.escape(share["name"])),
            parse_mode=ParseMode.HTML, reply_markup=_home_kb(lang),
        )
        return
    await q.answer()
    await q.edit_message_text(
        t(lang, "pshare_pick_agent", name=html.escape(share["name"])),
        parse_mode=ParseMode.HTML,
        reply_markup=pshare_pick_agent_kb(agents, share["share_id"], lang),
    )


async def on_apply_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    aid = int(q.data.split(":")[3])
    agent = await get_agent(aid)
    if not agent or agent["user_id"] != q.from_user.id:
        await q.answer(t(lang, "pshare_stale"), show_alert=True)
        return
    await update_agent(aid, user_prompt=share["body"])
    await set_preset_share_status(share["share_id"], "accepted")
    await q.answer()
    await q.edit_message_text(
        t(lang, "pshare_applied", name=html.escape(share["name"]),
          agent=html.escape(agent.get("name") or str(aid))),
        parse_mode=ParseMode.HTML, reply_markup=_home_kb(lang),
    )


async def on_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    await create_user_preset(q.from_user.id, share["name"], share["body"])
    await set_preset_share_status(share["share_id"], "accepted")
    await q.answer()
    await q.edit_message_text(
        t(lang, "pshare_saved", name=html.escape(share["name"])),
        parse_mode=ParseMode.HTML, reply_markup=_home_kb(lang),
    )


async def on_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    share, lang = await _load(update)
    if not share:
        return
    await set_preset_share_status(share["share_id"], "rejected")
    await q.answer()
    await q.edit_message_text(
        t(lang, "pshare_rejected", name=html.escape(share["name"])),
        parse_mode=ParseMode.HTML, reply_markup=_home_kb(lang),
    )


def get_preset_share_handlers() -> list:
    """Global recipient-side handlers for shared-preset offers."""
    return [
        CallbackQueryHandler(on_view, pattern=r"^pshare:view:\d+$"),
        CallbackQueryHandler(on_offer, pattern=r"^pshare:offer:\d+$"),
        CallbackQueryHandler(on_apply_to, pattern=r"^pshare:applyto:\d+:\d+$"),
        CallbackQueryHandler(on_apply, pattern=r"^pshare:apply:\d+$"),
        CallbackQueryHandler(on_save, pattern=r"^pshare:save:\d+$"),
        CallbackQueryHandler(on_reject, pattern=r"^pshare:reject:\d+$"),
    ]
