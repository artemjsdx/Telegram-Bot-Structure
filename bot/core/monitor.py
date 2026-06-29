"""
Channel-post handler: the heart of the bot.

On every new channel post it resolves the agent bound to that channel, builds the
rewrite prompt (optional system block + the agent's instruction), runs the AI call
through the serial queue, then either previews the result in the owner's DM or
publishes it. Publishing follows the agent's struct_mode:
  • 'edit'   — edit the post in place (editMessageText/Caption);
  • 'resend' — delete the original and send a fresh post, keeping media by file_id.
Forwarded posts can't be edited, so when the agent is set to react to them they
always go through resend; otherwise they're skipped. Albums (media groups) arrive
as several updates with the same media_group_id — we buffer them briefly and
process the whole album once. Every attempt is logged for stats/admin.
"""
from __future__ import annotations

import asyncio
import logging
import time

from telegram import Message, Update
from telegram.ext import ContextTypes

from core.ai_client import resolve_creds_from_agent
from core.formatter import get_system_prompt
from core.limits import (
    CAPTION_LIMIT, TEXT_LIMIT, generate_within, hard_truncate, visible_len,
)
from core.preview import send_preview
from core.queue import queue
from core.replacer import replace_post
from core.resend import resend_post
from core.sanitize import sanitize_html
from db.storage import (
    get_agent_by_channel,
    get_user,
    log_post_stat,
    log_request,
)
from config import DEFAULT_LANG
from providers import get_provider
from texts import t

logger = logging.getLogger(__name__)

# How long to wait for the remaining items of an album before processing it.
# Album items arrive as separate updates back-to-back; 1.6s comfortably covers
# the gap without making single posts feel sluggish (they skip the buffer).
ALBUM_DEBOUNCE = 1.6


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg:
        return
    if msg.media_group_id:
        await _buffer_album(context, msg)
        return
    await _process_post(context, [msg])


# ───── album buffering ─────
async def _buffer_album(context: ContextTypes.DEFAULT_TYPE, msg: Message) -> None:
    """Collect items sharing a media_group_id, debounced, then process once."""
    mgid = msg.media_group_id
    buf = context.bot_data.setdefault("album_buf", {})
    entry = buf.get(mgid)
    if entry is None:
        entry = {"messages": [], "task": None}
        buf[mgid] = entry
    entry["messages"].append(msg)
    if entry["task"]:
        entry["task"].cancel()
    entry["task"] = asyncio.create_task(_flush_album(context, mgid))


async def _flush_album(context: ContextTypes.DEFAULT_TYPE, mgid: str) -> None:
    try:
        await asyncio.sleep(ALBUM_DEBOUNCE)
    except asyncio.CancelledError:
        return
    entry = context.bot_data.get("album_buf", {}).pop(mgid, None)
    if not entry or not entry["messages"]:
        return
    msgs = sorted(entry["messages"], key=lambda m: m.message_id)
    await _process_post(context, msgs)


# ───── core processing ─────
async def _process_post(context: ContextTypes.DEFAULT_TYPE, msgs: list[Message]) -> None:
    primary = next((m for m in msgs if (m.text or m.caption)), msgs[0])
    channel_id = primary.chat_id

    agent = await get_agent_by_channel(channel_id)
    if not agent:
        return

    mode = agent.get("struct_mode") or "edit"
    react_fwd = bool(agent.get("react_forwarded", 0))
    is_forwarded = any(m.forward_origin is not None for m in msgs)
    if is_forwarded:
        if not react_fwd:
            logger.info("Skipping forwarded post in channel %s", channel_id)
            return
        # A bot can't edit a forwarded message — react by resending instead.
        mode = "resend"

    user_id = agent["user_id"]
    user = await get_user(user_id)
    if not user or user.get("is_banned"):
        return

    post_plain = primary.text or primary.caption or ""
    if not post_plain.strip():
        logger.info("Skipping empty post in channel %s", channel_id)
        return

    # Give the model the post with its original Telegram formatting rendered as
    # HTML so it can choose which styling to preserve; falls back to plain text.
    post_html = primary.text_html or primary.caption_html or post_plain

    has_media = any(_has_media(m) for m in msgs)
    limit = CAPTION_LIMIT if has_media else TEXT_LIMIT

    prompt = agent.get("user_prompt") or ""
    content_parts = []
    if bool(agent.get("sys_prompt", 1)):
        sys_text = get_system_prompt()
        if sys_text:
            content_parts.append(
                f"[SYSTEM INSTRUCTIONS]\n{sys_text}\n[/SYSTEM INSTRUCTIONS]\n"
            )
    content_parts.append(
        f"{prompt}\n\nPost (original Telegram HTML formatting — keep the styling "
        f"you don't change):\n{post_html}"
    )
    messages = [{"role": "user", "content": "\n".join(content_parts)}]

    creds = resolve_creds_from_agent(agent)
    provider_name, model = creds["provider"], creds["model"]
    prov = get_provider(provider_name)

    async def call(convo: list[dict]) -> str:
        return await queue.enqueue(
            lambda: prov.chat(creds["api_base"], creds["api_key"], model, convo)
        )

    logger.info(
        "Processing post chan=%s agent=%s provider=%s model=%s mode=%s fwd=%s "
        "media=%s preview=%s len=%d items=%d",
        channel_id, agent["agent_id"], provider_name, model, mode, is_forwarded,
        has_media, bool(user.get("preview_mode")), len(post_plain), len(msgs),
    )

    t0 = time.monotonic()
    try:
        ai_response = await generate_within(call, messages, limit)
        # Final safety net: if the model never fit the limit, hard-truncate so the
        # publish call can't fail on a too-long caption/text.
        if visible_len(sanitize_html(ai_response)) > limit:
            logger.warning("Result still over %d chars after retries; truncating", limit)
            ai_response = hard_truncate(ai_response, limit)
        response_ms = int((time.monotonic() - t0) * 1000)

        if user.get("preview_mode"):
            await send_preview(context, user, primary, ai_response)
        elif mode == "resend":
            await resend_post(context.bot, msgs, ai_response)
        else:
            await replace_post(context.bot, primary, ai_response)

        await log_post_stat(user_id, channel_id, response_ms, True)
        await log_request(user_id, channel_id, provider_name, model, True, response_ms)
        logger.info("Post handled in channel %s (%d ms)", channel_id, response_ms)
    except Exception as e:
        response_ms = int((time.monotonic() - t0) * 1000)
        logger.error("Error processing post in channel %s: %s", channel_id, e)
        await log_post_stat(user_id, channel_id, response_ms, False)
        await log_request(
            user_id, channel_id, provider_name, model, False, response_ms, str(e)
        )
        lang = user.get("lang") or DEFAULT_LANG
        chan_title = (primary.chat.title if primary.chat else None) or str(channel_id)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=t(lang, "post_failed_dm", channel=chan_title, error=str(e)[:600]),
            )
        except Exception as notify_err:  # noqa: BLE001
            logger.warning("Could not DM owner %s about post failure: %s", user_id, notify_err)


def _has_media(message: Message) -> bool:
    return bool(
        message.photo or message.video or message.document
        or message.animation or message.audio or message.voice
    )
