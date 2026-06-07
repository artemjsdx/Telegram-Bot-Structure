import logging
from telegram import Bot, Message
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def replace_post(bot: Bot, message: Message, new_text: str):
    """
    Replace channel post with AI-generated text.
    Text-only -> editMessageText (preserves views/reactions).
    Media post  -> deleteMessage + resend with new caption.
    """
    chat_id = message.chat_id
    msg_id = message.message_id

    if message.text and not message.photo and not message.video \
            and not message.document and not message.animation:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=new_text,
                parse_mode=ParseMode.HTML,
            )
            return
        except Exception as e:
            logger.warning(f"Edit failed ({e}), falling back to delete+send")

    # Delete original
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Could not delete message {msg_id}: {e}")

    # Resend with media if present
    try:
        if message.photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=message.photo[-1].file_id,
                caption=new_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.video:
            await bot.send_video(
                chat_id=chat_id,
                video=message.video.file_id,
                caption=new_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.document:
            await bot.send_document(
                chat_id=chat_id,
                document=message.document.file_id,
                caption=new_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.animation:
            await bot.send_animation(
                chat_id=chat_id,
                animation=message.animation.file_id,
                caption=new_text,
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=new_text,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Failed to send replacement message: {e}")
