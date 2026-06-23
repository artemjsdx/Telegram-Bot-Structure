"""
Tidy raw LLM output before it is sent to Telegram.

Two things routinely break parse_mode=HTML:
  • reasoning models prefix their reply with a <think>…</think> block;
  • many models wrap structure in tags Telegram's parser rejects
    (<br>, <p>, <div>, <ul>/<li>, <h1>…) → editMessage 400s with
    "unsupported start tag …".

We strip the reasoning blocks, turn break/block tags into plain newlines, and
drop every tag Telegram doesn't accept while KEEPING its inner text — so the
rewrite lands with its bold/italic/links intact instead of falling back to
formatting-less plain text. Anything still unsupported is caught by the
plain-text retry in replace_post, so a post is never lost to a formatting error.
"""
from __future__ import annotations

import re

_REASONING_TAGS = ("think", "thinking", "thought", "reason", "reasoning", "analysis")
_TAGS = "|".join(_REASONING_TAGS)
_REASONING_RE = re.compile(
    rf"<\s*(?:{_TAGS})\s*>.*?<\s*/\s*(?:{_TAGS})\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Tags Telegram's HTML parser accepts; every other tag is removed (its text is
# kept). Both the open and close of a non-allowed tag are dropped together, so
# the result stays balanced. Spoilers survive via <tg-spoiler>; the <span
# class="tg-spoiler"> spelling is downgraded to plain text (its </span> can't be
# told apart from a generic one, so keeping it would orphan a tag).
_ALLOWED = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "blockquote", "tg-spoiler", "tg-emoji",
}

_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_LI_OPEN_RE = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
# Opening or closing block tags become line breaks so paragraphs/lists survive.
_BLOCK_RE = re.compile(
    r"</?\s*(?:p|div|li|ul|ol|h[1-6]|section|article|header|footer|tr)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z0-9-]+)([^>]*?)\s*/?\s*>")
_TRAIL_WS_RE = re.compile(r"[ \t]+\n")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def strip_reasoning(text: str) -> str:
    """Remove closed <think>…</think>-style reasoning blocks and trim whitespace."""
    if not text:
        return text
    return _REASONING_RE.sub("", text).strip()


def _keep_tag(m: "re.Match") -> str:
    return m.group(0) if m.group(1).lower() in _ALLOWED else ""


def sanitize_html(text: str) -> str:
    """
    Make raw model output safe for parse_mode=HTML: drop reasoning blocks,
    convert <br>/block tags to newlines, bullet <li>, and strip any tag
    Telegram won't accept (keeping its inner text). Supported formatting tags
    (b/i/u/s/a/code/pre/blockquote/tg-spoiler/tg-emoji) pass through untouched.
    """
    if not text:
        return text
    text = strip_reasoning(text)
    text = _BR_RE.sub("\n", text)
    text = _LI_OPEN_RE.sub("\n• ", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub(_keep_tag, text)
    text = _TRAIL_WS_RE.sub("\n", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()
