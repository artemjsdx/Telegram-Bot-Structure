import logging

from telegram import Bot, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.sanitize import strip_reasoning

logger = logging.getLogger(__name__)


def _is_media(message: Message) -> bool:
    return bool(
        message.photo or message.video or message.document
        or message.animation or message.audio or message.voice
    )


async def replace_post(bot: Bot, message: Message, new_text: str) -> None:
    """
    Replace a channel post with AI-generated text *in place*.

    The post is NEVER deleted: a text post is edited via editMessageText, a
    media/file post via editMessageCaption (the attachment stays untouched).
    On an HTML parse error we retry the same edit as plain text so the content
    still lands; "message is not modified" is treated as success. Any other
    failure propagates so the caller can log it and notify the owner — the
    original post is left intact.
    """
    new_text = strip_reasoning(new_text)
    chat_id, msg_id = message.chat_id, message.message_id

    if _is_media(message):
        async def edit(parse_mode):
            await bot.edit_message_caption(
                chat_id=chat_id, message_id=msg_id,
                caption=new_text, parse_mode=parse_mode,
            )
    else:
        async def edit(parse_mode):
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=new_text, parse_mode=parse_mode,
            )

    try:
        await edit(ParseMode.HTML)
    except BadRequest as e:
        err = str(e).lower()
        if "not modified" in err:
            return
        if "parse" in err or "entit" in err or "tag" in err:
            logger.warning("HTML parse failed (%s); retrying edit as plain text", e)
            await edit(None)
            return
        raise
