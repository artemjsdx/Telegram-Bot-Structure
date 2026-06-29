"""
HTML → Telegram entity parser for the Telethon (autopost) path, extending
Telethon's built-in parser with spoiler support.

Telethon 1.36's html parser handles b/i/u/s, blockquote, code, pre and links,
but NOT <tg-spoiler> (Bot API supports it, MTProto via MessageEntitySpoiler does
too — Telethon just doesn't map a tag to it). We subclass its parser to also turn
<tg-spoiler>…</tg-spoiler> into a spoiler entity, reusing Telethon's own
UTF-16/surrogate offset machinery so offsets stay correct.

Custom emoji (<tg-emoji>) is intentionally NOT handled here: publishing premium
emoji needs a Premium account, so such tags fall through to plain text (the inner
emoji char survives, just without the custom-emoji effect).

Defensive import: if Telethon is absent the module still loads and parse() just
strips tags, so importing it never crashes the bot.
"""
from __future__ import annotations

import re

try:
    from telethon.extensions.html import HTMLToTelegramParser
    from telethon.helpers import add_surrogate, del_surrogate, strip_text
    from telethon.tl.types import MessageEntitySpoiler
    _OK = True
except Exception:  # noqa: BLE001
    _OK = False

_TAG_RE = re.compile(r"<[^>]+>")
_SPOILER_KEY = "tg-spoiler"


if _OK:
    class _SpoilerParser(HTMLToTelegramParser):
        """Adds <tg-spoiler> on top of Telethon's tag handling."""

        def handle_starttag(self, tag, attrs):
            is_spoiler = tag == "tg-spoiler" or (
                tag == "span" and dict(attrs).get("class") == "tg-spoiler")
            if is_spoiler:
                # Mirror the base class's bookkeeping for an opened entity.
                self._open_tags.appendleft(tag)
                self._open_tags_meta.appendleft(None)
                if _SPOILER_KEY not in self._building_entities:
                    self._building_entities[_SPOILER_KEY] = MessageEntitySpoiler(
                        offset=len(self.text), length=0)
                return
            super().handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            if tag == "tg-spoiler" or tag == "span":
                try:
                    self._open_tags.popleft()
                    self._open_tags_meta.popleft()
                except IndexError:
                    pass
                entity = self._building_entities.pop(_SPOILER_KEY, None)
                if entity:
                    self.entities.append(entity)
                return
            super().handle_endtag(tag)


def parse(html: str):
    """
    HTML → (clean_text, entities) including spoilers. Falls back to (tag-stripped
    text, []) when Telethon isn't available.
    """
    if not html:
        return html, []
    if not _OK:
        import html as ihtml
        return ihtml.unescape(_TAG_RE.sub("", html)), []
    parser = _SpoilerParser()
    parser.feed(add_surrogate(html))
    text = strip_text(parser.text, parser.entities)
    parser.entities.reverse()
    parser.entities.sort(key=lambda e: e.offset)
    return del_surrogate(text), parser.entities
