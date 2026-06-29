"""
ReAct-style research loop layered on top of a plain chat-completion call.

The providers here expose only chat(messages)->text (no native tool-calling), so
"let the model decide to search the web" is done with a tiny text protocol:

  • the model asks to search by emitting one or more lines:
        ПОИСК: запрос1 | запрос2 | запрос3
    (all queries run in parallel);
  • it asks for the full text of a previously-returned result by id:
        РАСКРЫТЬ: 2, 5
    (truncated snippets are returned by default; expansions run in parallel too);
  • when it emits NEITHER directive, its reply is the final post.

Each round feeds the results back as a user message with stable [id] labels, a
URL and the source's date (so the model can judge freshness). Bounded by
max_rounds; on exhaustion we ask once for a final answer.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

from core import websearch

logger = logging.getLogger(__name__)

_SEARCH_RE = re.compile(r"^\s*(?:ПОИСК|SEARCH)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_EXPAND_RE = re.compile(r"^\s*(?:РАСКРЫТЬ|РАСКРОЙ|EXPAND)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_INT_RE = re.compile(r"\d+")

_RESULTS_HEADER = "📡 РЕЗУЛЬТАТЫ ПОИСКА:\n\n"
_RESULTS_FOOTER = (
    "\n\n---\nИспользуй эти данные. Можешь сделать ещё ПОИСК или РАСКРЫТЬ "
    "конкретный результат по его [номеру], если данных не хватает. Когда информации "
    "достаточно — выдай ТОЛЬКО готовый пост, без команд ПОИСК/РАСКРЫТЬ и без пояснений."
)
_FINALIZE = (
    "Лимит раундов поиска исчерпан. Выдай финальный готовый пост на основе уже "
    "собранной информации. Без команд ПОИСК/РАСКРЫТЬ и без пояснений."
)

# Injected into the model's context (by the caller) when web search is enabled.
RESEARCH_INSTRUCTIONS = (
    "[ВЕБ-ПОИСК ДОСТУПЕН]\n"
    "Если для точного и актуального поста тебе не хватает данных (например, нужны "
    "текущие лимиты/условия сервиса, детали новости, проверка фактов), ты можешь "
    "искать в интернете. Чтобы выполнить поиск, ответь ТОЛЬКО командой (без текста поста):\n"
    "  ПОИСК: запрос1 | запрос2 | запрос3\n"
    "Можно несколько запросов через «|» — они выполнятся параллельно. В ответ "
    "придут результаты с номерами [N], URL, ДАТОЙ источника и фрагментом текста.\n"
    "Если фрагмента мало — запроси полную версию конкретного результата командой:\n"
    "  РАСКРЫТЬ: 2, 5\n"
    "Всегда сверяйся с ДАТОЙ источника, чтобы информация была актуальной. Не выдумывай "
    "факты — бери их только из результатов поиска или из исходного поста. Когда данных "
    "достаточно, выдай ТОЛЬКО готовый пост без каких-либо команд.\n"
)


def _parse_search(text: str, cfg: dict) -> list[str]:
    queries: list[str] = []
    for line in _SEARCH_RE.findall(text or ""):
        for part in re.split(r"[|\n]", line):
            q = part.strip().strip("«»\"'`").strip()
            if q and q not in queries:
                queries.append(q)
    return queries[: cfg.get("max_queries", 5)]


def _parse_expand(text: str) -> list[int]:
    ids: list[int] = []
    for line in _EXPAND_RE.findall(text or ""):
        for m in _INT_RE.findall(line):
            n = int(m)
            if n not in ids:
                ids.append(n)
    return ids[:10]


async def _expand_one(item: dict, rid: int, cfg: dict) -> str:
    page = await websearch.fetch_page(item["url"], cfg.get("full_chars", 6000))
    date = page.get("date") or item.get("date") or "неизвестна"
    body = page.get("text") or item.get("snippet") or "—"
    return (f"[{rid}] ПОЛНАЯ ВЕРСИЯ — {item.get('title') or item['url']}\n"
            f"URL: {item['url']}\nДата: {date}\n{body}")


async def run_with_research(
    call: Callable[[list[dict]], Awaitable[str]],
    messages: list[dict],
    cfg: dict,
) -> str:
    """
    Run the model with web-search capability. `call(messages)->text` is the raw
    provider call. cfg keys: enabled, results_n, snippet_chars, full_chars,
    max_rounds, max_queries, api_key. With web search disabled it's a passthrough.
    """
    if not cfg.get("enabled"):
        return await call(messages)

    convo = list(messages)
    registry: list[dict] = []
    rounds = max(1, int(cfg.get("max_rounds", 3)))

    for _ in range(rounds):
        result = await call(convo)
        queries = _parse_search(result, cfg)
        expands = _parse_expand(result)
        if not queries and not expands:
            return result  # final post

        convo = convo + [{"role": "assistant", "content": result}]
        blocks: list[str] = []

        if expands:
            tasks = [_expand_one(registry[i - 1], i, cfg)
                     for i in expands if 1 <= i <= len(registry)]
            if tasks:
                blocks.extend(await asyncio.gather(*tasks))

        if queries:
            searches = await asyncio.gather(*[
                websearch.search_and_read(
                    q, cfg.get("results_n", 5), cfg.get("snippet_chars", 1500),
                    cfg.get("api_key"))
                for q in queries
            ])
            for q, items in zip(queries, searches):
                if not items:
                    blocks.append(f"🔎 «{q}»: ничего не найдено.")
                    continue
                lines = [f"🔎 Результаты по запросу «{q}»:"]
                for it in items:
                    registry.append(it)
                    rid = len(registry)
                    date = it.get("date") or "дата неизвестна"
                    frag = it.get("text") or it.get("snippet") or "—"
                    lines.append(
                        f"[{rid}] {it.get('title') or it['url']}\n"
                        f"URL: {it['url']}\nДата: {date}\nФрагмент: {frag}"
                    )
                blocks.append("\n\n".join(lines))

        logger.info("research round: %d queries, %d expands, registry=%d",
                    len(queries), len(expands), len(registry))
        convo = convo + [{"role": "user", "content": _RESULTS_HEADER + "\n\n".join(blocks) + _RESULTS_FOOTER}]

    convo = convo + [{"role": "user", "content": _FINALIZE}]
    return await call(convo)
