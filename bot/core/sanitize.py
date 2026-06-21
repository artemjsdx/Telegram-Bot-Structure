"""
Tidy raw LLM output before it is sent to Telegram.

Reasoning models (gpt-5.5 and friends) prefix their reply with a
<think>…</think> block. Telegram's HTML parser rejects the unknown tag and the
edit 400s ("unsupported start tag think"). We drop those blocks here; anything
else unsupported is caught by the plain-text retry in replace_post, so a post is
never lost to a formatting error.
"""
from __future__ import annotations

import re

_REASONING_TAGS = ("think", "thinking", "thought", "reason", "reasoning", "analysis")
_TAGS = "|".join(_REASONING_TAGS)
_REASONING_RE = re.compile(
    rf"<\s*(?:{_TAGS})\s*>.*?<\s*/\s*(?:{_TAGS})\s*>",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning(text: str) -> str:
    """Remove closed <think>…</think>-style reasoning blocks and trim whitespace."""
    if not text:
        return text
    return _REASONING_RE.sub("", text).strip()
