"""
Resend mode: replace a channel post by deleting the original and sending a fresh
one, re-attaching the original media by file_id (no download, nothing stored).

Used when the agent's struct_mode is 'resend', and always for forwarded posts
(which Telegram won't let a bot edit). Media is reattached straight from the
file_id of the incoming message(s):
  • a plain text post  → delete + send_message;
  • a single media post → delete + the matching send_* with the new caption;
  • an album (media_group) → delete every item + one send_media_group, caption on
    the first item.

We send the new post FIRST and delete the originals only after it succeeds, so a
failure never loses the content. HTML is tried first and, on a parse error, the
same send is retried as plain text (mirrors core.replacer).
"""
from __future__ import annotations

import logging

from telegram import (
    Bot, Message,
    InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.sanitize import sanitize_html

logger = logging.getLogger(__name__)


def _is_media(message: Message) -> bool:
    return bool(
        message.photo or message.video or message.document
        or message.animation or message.audio or message.voice
    )


def _file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    for attr in ("video", "document", "animation", "audio", "voice"):
        obj = getattr(message, attr, None)
        if obj:
            return obj.file_id
    return None


def _is_parse_error(e: BadRequest) -> bool:
    err = str(e).lower()
    return "parse" in err or "entit" in err or "tag" in err


async def _send_single(bot: Bot, chat_id: int, src: Message, caption: str) -> Message:
    """Resend one media message by file_id with the new caption (HTML→plain)."""
    fid = _file_id(src)
    senders = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "animation": bot.send_animation,
        "audio": bot.send_audio,
        "voice": bot.send_voice,
    }
    if src.photo:
        kind = "photo"
    else:
        kind = next((k for k in senders if getattr(src, k, None)), "document")
    send = senders[kind]
    kw = {"chat_id": chat_id, kind: fid, "caption": caption}
    try:
        return await send(parse_mode=ParseMode.HTML, **kw)
    except BadRequest as e:
        if _is_parse_error(e):
            logger.warning("resend single HTML parse failed (%s); retrying plain", e)
            return await send(parse_mode=None, **kw)
        raise


def _input_media(src: Message, caption: str | None, parse_mode):
    fid = _file_id(src)
    if src.photo:
        return InputMediaPhoto(fid, caption=caption, parse_mode=parse_mode)
    if src.video:
        return InputMediaVideo(fid, caption=caption, parse_mode=parse_mode)
    if src.audio:
        return InputMediaAudio(fid, caption=caption, parse_mode=parse_mode)
    return InputMediaDocument(fid, caption=caption, parse_mode=parse_mode)


async def _send_album(bot: Bot, chat_id: int, items: list[Message], caption: str) -> None:
    """Resend an album; the caption rides on the first item only."""
    def build(parse_mode):
        media = []
        for i, m in enumerate(items):
            media.append(_input_media(m, caption if i == 0 else None, parse_mode))
        return media

    try:
        await bot.send_media_group(chat_id=chat_id, media=build(ParseMode.HTML))
    except BadRequest as e:
        if _is_parse_error(e):
            logger.warning("resend album HTML parse failed (%s); retrying plain", e)
            await bot.send_media_group(chat_id=chat_id, media=build(None))
        else:
            raise


async def _send_text(bot: Bot, chat_id: int, text: str) -> Message:
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        if _is_parse_error(e):
            logger.warning("resend text HTML parse failed (%s); retrying plain", e)
            return await bot.send_message(
                chat_id=chat_id, text=text, disable_web_page_preview=True,
            )
        raise


async def resend_post(bot: Bot, messages: list[Message], new_text: str) -> None:
    """
    Delete the given post (1 message, or all items of an album) and send a fresh
    structured post in its place, keeping any media by file_id. The new post is
    sent before the originals are removed, so nothing is lost on failure.
    """
    if not messages:
        return
    new_text = sanitize_html(new_text)
    chat_id = messages[0].chat_id
    media_items = [m for m in messages if _is_media(m)]

    if not media_items:
        await _send_text(bot, chat_id, new_text)
    elif len(media_items) == 1:
        await _send_single(bot, chat_id, media_items[0], new_text)
    else:
        await _send_album(bot, chat_id, media_items, new_text)

    for m in messages:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=m.message_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("resend: could not delete original %s: %s", m.message_id, e)
