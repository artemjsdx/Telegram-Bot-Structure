"""
Channel-post handler: the heart of the bot.

On every new channel post it resolves the agent bound to that channel, builds the
rewrite prompt (optional system block + the agent's instruction), runs the AI call
through the serial queue, then either previews the result in the owner's DM or
replaces the post in place. Every attempt is logged for stats/admin.
"""
from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from core.ai_client import resolve_creds_from_agent
from core.formatter import get_system_prompt
from core.preview import send_preview
from core.queue import queue
from core.replacer import replace_post
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


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg:
        return

    channel_id = msg.chat_id
    agent = await get_agent_by_channel(channel_id)
    if not agent:
        return

    # Forwarded posts carry a "Forwarded from" header and aren't the channel's
    # own content, so leave them untouched — the agent must not react to them.
    if msg.forward_origin is not None:
        logger.info("Skipping forwarded post in channel %s", channel_id)
        return

    user_id = agent["user_id"]
    user = await get_user(user_id)
    if not user or user.get("is_banned"):
        return

    post_plain = msg.text or msg.caption or ""
    if not post_plain.strip():
        logger.info("Skipping empty post in channel %s", channel_id)
        return

    # Give the model the post with its original Telegram formatting rendered as
    # HTML (bold, italic, underline, strikethrough, spoiler, code, links, custom
    # emoji, …) so it can choose which styling to preserve; falls back to plain
    # text when the post has no entities.
    post_html = msg.text_html or msg.caption_html or post_plain

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

    logger.info(
        "Processing post chan=%s agent=%s provider=%s model=%s preview=%s len=%d",
        channel_id, agent["agent_id"], provider_name, model,
        bool(user.get("preview_mode")), len(post_plain),
    )

    t0 = time.monotonic()
    try:
        ai_response = await queue.enqueue(
            lambda: prov.chat(creds["api_base"], creds["api_key"], model, messages)
        )
        response_ms = int((time.monotonic() - t0) * 1000)

        if user.get("preview_mode"):
            await send_preview(context, user, msg, ai_response)
        else:
            await replace_post(context.bot, msg, ai_response)

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
        # Tell the owner in DM why their post wasn't rewritten (plain text — the
        # error string may contain characters that would break HTML parsing).
        lang = user.get("lang") or DEFAULT_LANG
        chan_title = (msg.chat.title if msg.chat else None) or str(channel_id)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=t(lang, "post_failed_dm", channel=chan_title, error=str(e)[:600]),
            )
        except Exception as notify_err:  # noqa: BLE001
            logger.warning("Could not DM owner %s about post failure: %s", user_id, notify_err)
