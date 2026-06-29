"""
Autoposting worker (MTProto userbot).

A single background loop polls every enabled config on its own interval (with
jitter and a per-window send cap for anti-ban) and, per its mode:
  • forward   — copy each new source message to every target (forward, with a
                send-as-new fallback when forwarding is restricted);
  • structure — rewrite each new source message via the agent's AI (+date +web
                search) using the autopost prompt, then post to every target;
  • digest    — gather up to digest_size recent messages with date/time/nick/id
                metadata, let the model extract a theme and write ONE post (or
                decide not to post), then publish; recent own posts are given as
                context so it keeps continuity and can edit its last N.

The AI plumbing (provider, current-Moscow-time line, web-search ReAct loop,
length feedback) is shared with the channel pipeline. Big media moves through
MTProto, which handles files up to ~2 GB (vs Bot API's small limits).
"""
from __future__ import annotations

import asyncio
import html as ihtml
import logging
import random
import time

from core import tg_client
from core.ai_client import resolve_creds_from_agent
from core.clock import current_time_line
from core.formatter import get_system_prompt
from core.limits import TEXT_LIMIT, generate_within, hard_truncate, visible_len
from core.queue import queue
from core.research import RESEARCH_INSTRUCTIONS, run_with_research
from core.sanitize import sanitize_html
from db.storage import (
    get_account, get_agent, get_config, get_enabled_configs, get_recent_sent,
    get_sources, get_targets, count_sent_since, record_sent, update_source_cursor,
)
from providers import get_provider

logger = logging.getLogger(__name__)

TICK = 10.0           # base loop granularity (seconds)
NO_POST = "НЕ ПОСТИТЬ"  # sentinel: the model declines to post this round
EDIT_RE_HINT = "ПРАВКА"


def _research_cfg(agent: dict) -> dict:
    return {
        "enabled": bool(agent.get("web_search", 0)),
        "results_n": int(agent.get("web_results") or 5),
        "snippet_chars": int(agent.get("web_snippet") or 1500),
        "full_chars": max(2000, int(agent.get("web_snippet") or 1500) * 4),
        "max_rounds": int(agent.get("web_rounds") or 3),
        "api_key": (agent.get("web_key") or "").strip() or None,
    }


async def _ai_post(agent: dict, user_content: str, limit: int = TEXT_LIMIT) -> str:
    """Run the agent's model on user_content, with date + optional web search."""
    creds = resolve_creds_from_agent(agent)
    prov = get_provider(creds["provider"])
    model = creds["model"]

    parts = [f"[CONTEXT]\n{current_time_line('ru')}\n[/CONTEXT]\n"]
    if bool(agent.get("sys_prompt", 1)):
        sys_text = get_system_prompt()
        if sys_text:
            parts.append(f"[SYSTEM INSTRUCTIONS]\n{sys_text}\n[/SYSTEM INSTRUCTIONS]\n")
    if bool(agent.get("web_search", 0)):
        parts.append(RESEARCH_INSTRUCTIONS)
    parts.append(user_content)
    messages = [{"role": "user", "content": "\n".join(parts)}]

    cfg = _research_cfg(agent)

    async def base_call(convo):
        return await queue.enqueue(
            lambda: prov.chat(creds["api_base"], creds["api_key"], model, convo)
        )

    async def call(convo):
        return await run_with_research(base_call, convo, cfg)

    out = await generate_within(call, messages, limit)
    if visible_len(sanitize_html(out)) > limit:
        out = hard_truncate(out, limit)
    return out


async def _send_html(client, target: int, text: str):
    """Send text to a target as HTML, falling back to plain on a parse error."""
    try:
        return await client.send_message(target, text, parse_mode="html",
                                         link_preview=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("autopost html send failed (%s); retry plain", e)
        import re
        plain = re.sub(r"<[^>]+>", "", text)
        return await client.send_message(target, ihtml.unescape(plain), link_preview=False)


class AutopostManager:
    """Singleton background worker; mirrors QueueManager's lifecycle."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._next_run: dict[int, float] = {}

    def start(self) -> None:
        if not tg_client.available():
            logger.warning("Autopost worker NOT started — Telethon unavailable.")
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("Autopost worker started.")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await tg_client.disconnect_all()

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                configs = await get_enabled_configs()
                now = time.monotonic()
                for cfg in configs:
                    if now >= self._next_run.get(cfg["config_id"], 0):
                        try:
                            await self._process(cfg)
                        except Exception as e:  # noqa: BLE001
                            logger.error("autopost config %s failed: %s",
                                         cfg["config_id"], e)
                        interval = max(TICK, float(cfg.get("poll_interval") or 60))
                        jitter = random.uniform(0, float(cfg.get("jitter") or 0))
                        self._next_run[cfg["config_id"]] = time.monotonic() + interval + jitter
            except Exception as e:  # noqa: BLE001
                logger.error("autopost loop error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=TICK)
            except asyncio.TimeoutError:
                pass

    # ───── per-config processing ─────
    async def _process(self, cfg: dict) -> None:
        config_id = cfg["config_id"]
        account = await get_account(cfg["account_id"]) if cfg.get("account_id") else None
        if not account:
            return
        client = await tg_client.get_client(account)
        if not client:
            return

        # Anti-ban: respect the per-window send cap.
        window = int(cfg.get("window_sec") or 3600)
        cap = int(cfg.get("max_per_window") or 0)
        if cap > 0:
            sent = await count_sent_since(config_id, int(time.time()) - window)
            if sent >= cap:
                logger.info("autopost %s: window cap reached (%d/%d)", config_id, sent, cap)
                return

        targets = await get_targets(config_id)
        sources = await get_sources(config_id)
        if not targets or not sources:
            return

        mode = cfg.get("mode") or "forward"
        agent = await get_agent(cfg["agent_id"])
        if mode in ("structure", "digest") and not agent:
            return

        if mode == "digest":
            await self._do_digest(client, cfg, agent, sources, targets)
        else:
            await self._do_stream(client, cfg, agent, sources, targets, mode)

    async def _do_stream(self, client, cfg, agent, sources, targets, mode) -> None:
        """forward / structure: react to each NEW source message since the cursor."""
        config_id = cfg["config_id"]
        for src in sources:
            try:
                entity = await client.get_entity(src["chat_id"])
            except Exception as e:  # noqa: BLE001
                logger.warning("autopost: cannot resolve source %s: %s", src["chat_id"], e)
                continue
            last_id = int(src.get("last_seen_id") or 0)
            new_msgs = []
            try:
                async for m in client.iter_messages(entity, min_id=last_id, limit=20, reverse=True):
                    new_msgs.append(m)
            except Exception as e:  # noqa: BLE001
                logger.warning("autopost: iter_messages failed for %s: %s", src["chat_id"], e)
                continue
            if not new_msgs:
                continue

            for m in new_msgs:
                text = m.message or ""
                try:
                    if mode == "forward":
                        for tgt in targets:
                            sent_msg = await self._forward_one(client, entity, m, tgt["chat_id"])
                            if sent_msg is not None:
                                await record_sent(config_id, tgt["chat_id"],
                                                  getattr(sent_msg, "id", 0), int(time.time()))
                    else:  # structure
                        if not text.strip():
                            continue
                        prompt = cfg.get("prompt") or ""
                        content = (f"{prompt}\n\nИсходное сообщение (источник — "
                                   f"{'канал' if src.get('kind') == 'channel' else 'чат'}):\n{text}")
                        result = await _ai_post(agent, content, TEXT_LIMIT)
                        for tgt in targets:
                            sent_msg = await _send_html(client, tgt["chat_id"], result)
                            await record_sent(config_id, tgt["chat_id"],
                                              getattr(sent_msg, "id", 0), int(time.time()))
                    await update_source_cursor(src["source_id"], m.id)
                except tg_client.FloodWaitError as e:  # type: ignore[attr-defined]
                    logger.warning("autopost FloodWait %ss on config %s", getattr(e, "seconds", "?"), config_id)
                    return
                except Exception as e:  # noqa: BLE001
                    logger.error("autopost stream item failed: %s", e)
                    await update_source_cursor(src["source_id"], m.id)

    async def _forward_one(self, client, from_entity, message, target_chat):
        """Forward a message; fall back to copying its text if forwarding is blocked."""
        try:
            return await client.forward_messages(target_chat, message.id, from_entity)
        except Exception as e:  # noqa: BLE001
            logger.info("forward blocked (%s); copying instead", e)
            try:
                if message.media:
                    return await client.send_file(target_chat, message.media,
                                                  caption=(message.message or "")[:1024])
                if message.message:
                    return await client.send_message(target_chat, message.message, link_preview=False)
            except Exception as e2:  # noqa: BLE001
                logger.warning("copy fallback failed: %s", e2)
            return None

    async def _do_digest(self, client, cfg, agent, sources, targets) -> None:
        """Collect recent messages with metadata → one themed post (or skip)."""
        config_id = cfg["config_id"]
        size = max(1, min(300, int(cfg.get("digest_size") or 100)))
        per_source = max(1, size // max(1, len(sources)))

        blocks: list[str] = []
        max_id_by_source: dict[int, int] = {}
        for src in sources:
            try:
                entity = await client.get_entity(src["chat_id"])
            except Exception as e:  # noqa: BLE001
                logger.warning("digest: cannot resolve source %s: %s", src["chat_id"], e)
                continue
            kind = "канал" if src.get("kind") == "channel" else "чат"
            last_id = int(src.get("last_seen_id") or 0)
            collected = []
            try:
                async for m in client.iter_messages(entity, min_id=last_id, limit=per_source, reverse=True):
                    if not (m.message or "").strip():
                        continue
                    collected.append(m)
            except Exception as e:  # noqa: BLE001
                logger.warning("digest: iter failed for %s: %s", src["chat_id"], e)
                continue
            for m in collected:
                when = m.date.strftime("%Y-%m-%d %H:%M:%S") if m.date else "—"
                nick = await self._sender_label(client, m)
                blocks.append(f"[{when} | {kind} | {nick} | id{m.id}] {m.message.strip()}")
                max_id_by_source[src["source_id"]] = max(max_id_by_source.get(src["source_id"], last_id), m.id)

        if not blocks:
            return

        recent_own = await get_recent_sent(config_id, int(cfg.get("edit_last_n") or 0))
        own_note = ""
        if recent_own:
            own_note = ("\n\nТвои недавние посты (для преемственности, не дублируй их):\n"
                        + "\n".join(f"- id{r['message_id']}" for r in recent_own))

        prompt = cfg.get("prompt") or ""
        content = (
            f"{prompt}\n\n"
            f"Ниже — до {len(blocks)} сообщений из отслеживаемых источников с метаданными "
            f"[дата время | тип | автор | id]. Определи тему по своей инструкции и напиши "
            f"ОДИН готовый пост. Если стоящей темы нет — ответь ровно «{NO_POST}» и ничего больше."
            f"{own_note}\n\n=== СООБЩЕНИЯ ===\n" + "\n".join(blocks)
        )
        result = await _ai_post(agent, content, TEXT_LIMIT)

        plain = sanitize_html(result)
        if not plain.strip() or NO_POST.lower() in plain.lower()[:40]:
            logger.info("digest %s: model declined to post", config_id)
            for sid, mid in max_id_by_source.items():
                await update_source_cursor(sid, mid)
            return

        for tgt in targets:
            try:
                sent_msg = await _send_html(client, tgt["chat_id"], result)
                await record_sent(config_id, tgt["chat_id"], getattr(sent_msg, "id", 0), int(time.time()))
            except Exception as e:  # noqa: BLE001
                logger.error("digest send failed: %s", e)
        for sid, mid in max_id_by_source.items():
            await update_source_cursor(sid, mid)

    async def _sender_label(self, client, message) -> str:
        try:
            sender = await message.get_sender()
            if sender is None:
                return "—"
            uname = getattr(sender, "username", None)
            if uname:
                return "@" + uname
            name = getattr(sender, "first_name", None) or getattr(sender, "title", None)
            return name or "—"
        except Exception:  # noqa: BLE001
            return "—"


autopost = AutopostManager()
