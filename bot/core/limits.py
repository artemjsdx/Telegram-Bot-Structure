"""
Telegram length limits + a feedback loop that asks the model to shorten.

Telegram counts the *visible* text (entities/tags don't count toward the limit),
so we measure length on the tag-stripped text. A media post's caption is capped
at 1024 chars, a plain text message at 4096. When the model's rewrite overshoots,
we hand the result back with a "too long, shorten to N" instruction and retry a
couple of times; if it still overshoots, the caller hard-truncates as a last
resort so a post is never lost.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable

from core.sanitize import sanitize_html

CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096

_TAG_RE = re.compile(r"<[^>]+>")


def visible_len(text: str) -> int:
    """Length Telegram actually counts: the text with HTML tags removed."""
    return len(_TAG_RE.sub("", text or ""))


def hard_truncate(text: str, limit: int) -> str:
    """Last-resort cut on the sanitized text; drops tags to avoid splitting one."""
    text = sanitize_html(text)
    if visible_len(text) <= limit:
        return text
    plain = _TAG_RE.sub("", text)
    return plain[: max(0, limit - 1)].rstrip() + "…"


async def generate_within(
    call: Callable[[list[dict]], Awaitable[str]],
    messages: list[dict],
    limit: int,
    *,
    max_retries: int = 2,
) -> str:
    """
    Run `call(messages)` and, while the sanitized result exceeds `limit` visible
    chars, append a shorten instruction and retry (up to max_retries). Returns the
    best raw model output we got — still sanitize/limit-check downstream before
    sending. The returned text may exceed the limit if the model never complied.
    """
    result = await call(messages)
    if visible_len(sanitize_html(result)) <= limit:
        return result

    convo = list(messages)
    for _ in range(max_retries):
        over = visible_len(sanitize_html(result))
        convo = convo + [
            {"role": "assistant", "content": result},
            {"role": "user", "content": (
                f"Твой ответ слишком длинный: {over} символов, а лимит Telegram — "
                f"{limit}. Сократи и переработай текст так, чтобы он уместился в "
                f"{limit} символов (считаются видимые символы, без HTML-тегов), "
                f"сохранив смысл, структуру и форматирование. Верни только готовый "
                f"пост, без пояснений."
            )},
        ]
        result = await call(convo)
        if visible_len(sanitize_html(result)) <= limit:
            return result
    return result
