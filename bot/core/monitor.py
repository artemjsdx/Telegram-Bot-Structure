import logging
from telegram import Update
from telegram.ext import ContextTypes

from db.storage import get_user_by_channel
from core.ai_client import chat
from core.formatter import get_system_prompt
from core.replacer import replace_post

logger = logging.getLogger(__name__)


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg:
        return

    channel_id = msg.chat_id
    user = await get_user_by_channel(channel_id)
    if not user or not user.get("setup_done"):
        return

    post_text = msg.text or msg.caption or ""
    if not post_text.strip():
        logger.info(f"Skipping empty post in channel {channel_id}")
        return

    api_base = user["api_base"]
    api_key = user["api_key"]
    model = user["model_id"]
    user_prompt = user["user_prompt"]
    sys_prompt_enabled = bool(user.get("sys_prompt", 1))

    content_parts = []
    if sys_prompt_enabled:
        sys_text = get_system_prompt()
        if sys_text:
            content_parts.append(f"[SYSTEM INSTRUCTIONS]\n{sys_text}\n[/SYSTEM INSTRUCTIONS]\n")

    content_parts.append(f"{user_prompt}\n\nPost:\n{post_text}")

    full_content = "\n".join(content_parts)

    messages = [{"role": "user", "content": full_content}]

    logger.info(
        f"Processing post in channel {channel_id} | "
        f"len={len(post_text)} | model={model} | "
        f"sys_prompt={'ON' if sys_prompt_enabled else 'OFF'} | "
        f"total_content_len={len(full_content)}"
    )

    try:
        ai_response = await chat(api_base, api_key, model, messages)
        await replace_post(context.bot, msg, ai_response)
        logger.info(f"Post replaced in channel {channel_id}")
    except Exception as e:
        logger.error(f"Error processing post in channel {channel_id}: {e}")
