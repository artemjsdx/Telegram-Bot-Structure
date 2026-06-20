"""
Async CRUD layer for FavoriteStructure v2.0.
All DB access goes through this module — no raw SQL elsewhere.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import aiosqlite
from config import DB_PATH
from db.models import create_tables


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create DB directory, tables and indexes (idempotent)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await create_tables(db)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_user(row: aiosqlite.Row) -> dict:
    """Convert a DB row to a plain dict, deserializing JSON fields."""
    d = dict(row)
    for field, default in (("channel_ids", []), ("chan_titles", {})):
        raw = d.get(field)
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw)
            except (ValueError, TypeError):
                d[field] = default
        elif raw is None:
            d[field] = default
    return d


def _serialize_kwargs(kwargs: dict) -> dict:
    """JSON-serialize list/dict values so they can be stored in TEXT columns."""
    out = {}
    for k, v in kwargs.items():
        if isinstance(v, (list, dict)):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

async def get_user(user_id: int) -> Optional[dict]:
    """Return user row as dict, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return _row_to_user(row) if row else None


async def upsert_user(user_id: int, **kwargs) -> None:
    """
    Insert a new user row or update fields on an existing one.
    Lists and dicts are automatically JSON-serialized.
    """
    kwargs = _serialize_kwargs(kwargs)
    user = await get_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if user is None:
            fields = ["user_id"] + list(kwargs.keys())
            values = [user_id] + list(kwargs.values())
            placeholders = ",".join(["?"] * len(values))
            cols = ",".join(fields)
            await db.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})", values
            )
        else:
            if not kwargs:
                return
            sets = ", ".join(f"{k}=?" for k in kwargs)
            values = list(kwargs.values()) + [user_id]
            await db.execute(
                f"UPDATE users SET {sets} WHERE user_id=?", values
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Channel CRUD
# ---------------------------------------------------------------------------

async def get_channels_for_user(user_id: int) -> list[dict]:
    """Return all channel rows for a user (active and inactive)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE user_id=? ORDER BY rowid ASC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_user_by_channel(channel_id: int) -> Optional[dict]:
    """
    Find the user that owns an active channel.
    Joins channels → users to guarantee the channel is active.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT u.* FROM users u
            JOIN channels c ON c.user_id = u.user_id
            WHERE c.channel_id=? AND c.active=1
            LIMIT 1
            """,
            (channel_id,),
        ) as cur:
            row = await cur.fetchone()
            return _row_to_user(row) if row else None


async def add_channel(
    user_id: int,
    channel_id: int,
    chan_title: str = "",
    provider: str = "favoriteapi",
    prompt: str = "",
) -> None:
    """
    Add (or reactivate) a channel for a user.
    Keeps users.channel_ids and users.chan_titles JSON lists in sync.
    Idempotent: safe to call multiple times for the same pair.
    """
    # Ensure user row exists
    if await get_user(user_id) is None:
        await upsert_user(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO channels (channel_id, user_id, chan_title, active, prompt, provider)
            VALUES (?,?,?,1,?,?)
            ON CONFLICT(channel_id, user_id) DO UPDATE SET
                chan_title=excluded.chan_title,
                active=1,
                provider=excluded.provider
            """,
            (channel_id, user_id, chan_title, prompt, provider),
        )
        await db.commit()

    # Sync JSON lists on users row
    user = await get_user(user_id)
    channel_ids: list = user.get("channel_ids") or []
    chan_titles: dict = user.get("chan_titles") or {}

    if channel_id not in channel_ids:
        channel_ids.append(channel_id)
    chan_titles[str(channel_id)] = chan_title

    await upsert_user(user_id, channel_ids=channel_ids, chan_titles=chan_titles)


async def remove_channel(user_id: int, channel_id: int) -> None:
    """
    Deactivate a channel (soft-delete).
    Removes it from users.channel_ids / users.chan_titles JSON lists.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE channels SET active=0 WHERE channel_id=? AND user_id=?",
            (channel_id, user_id),
        )
        await db.commit()

    user = await get_user(user_id)
    if user is None:
        return

    channel_ids: list = [c for c in (user.get("channel_ids") or []) if c != channel_id]
    chan_titles: dict = {k: v for k, v in (user.get("chan_titles") or {}).items()
                        if k != str(channel_id)}

    await upsert_user(user_id, channel_ids=channel_ids, chan_titles=chan_titles)


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------

_AGENT_FIELDS = {
    "name", "provider", "api_base", "api_key", "model_id", "user_prompt", "sys_prompt",
}


async def create_agent(
    user_id: int,
    name: str,
    provider: str = "favoriteapi",
    api_base: str = "",
    api_key: str = "",
    model_id: str = "",
    user_prompt: str = "",
    sys_prompt: int = 1,
) -> int:
    """Create a new agent and return its agent_id."""
    if await get_user(user_id) is None:
        await upsert_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO agents
               (user_id, name, provider, api_base, api_key, model_id,
                user_prompt, sys_prompt, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user_id, name, provider, api_base, api_key, model_id,
             user_prompt, int(sys_prompt), int(time.time())),
        )
        await db.commit()
        return cur.lastrowid


async def get_agent(agent_id: int) -> Optional[dict]:
    """Return an agent row as dict, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agents WHERE agent_id=?", (agent_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_agents_for_user(user_id: int) -> list[dict]:
    """Return all agents owned by a user, oldest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agents WHERE user_id=? ORDER BY agent_id ASC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_agent(agent_id: int, **kwargs) -> None:
    """Update whitelisted fields on an agent."""
    fields = {k: v for k, v in kwargs.items() if k in _AGENT_FIELDS}
    if "sys_prompt" in fields:
        fields["sys_prompt"] = int(fields["sys_prompt"])
    if not fields:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [agent_id]
        await db.execute(
            f"UPDATE agents SET {sets} WHERE agent_id=?", vals
        )
        await db.commit()


async def delete_agent(agent_id: int) -> None:
    """Delete an agent and deactivate/unbind all its channels."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE channels SET active=0, agent_id=NULL WHERE agent_id=?",
            (agent_id,),
        )
        await db.execute("DELETE FROM agents WHERE agent_id=?", (agent_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# User presets CRUD (per-user "favorite" presets, shown atop the preset library)
# ---------------------------------------------------------------------------

async def create_user_preset(user_id: int, name: str, body: str) -> int:
    """Create a personal preset for a user and return its preset_id."""
    if await get_user(user_id) is None:
        await upsert_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO user_presets (user_id, name, body, created_at)
               VALUES (?,?,?,?)""",
            (user_id, name, body, int(time.time())),
        )
        await db.commit()
        return cur.lastrowid


async def get_user_presets(user_id: int) -> list[dict]:
    """Return a user's personal presets, newest first (favorites on top)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_presets WHERE user_id=? ORDER BY preset_id DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_user_preset(preset_id: int) -> Optional[dict]:
    """Return a single personal preset row as dict, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_presets WHERE preset_id=?", (preset_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_user_preset(preset_id: int) -> None:
    """Delete a personal preset by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_presets WHERE preset_id=?", (preset_id,))
        await db.commit()


async def get_agent_by_channel(channel_id: int) -> Optional[dict]:
    """
    Find the agent that owns an active channel (replaces get_user_by_channel
    for post processing). Returns the agent row as dict, or None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT a.* FROM agents a
            JOIN channels c ON c.agent_id = a.agent_id
            WHERE c.channel_id=? AND c.active=1
            LIMIT 1
            """,
            (channel_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_channel_to_agent(
    agent_id: int,
    user_id: int,
    channel_id: int,
    chan_title: str = "",
) -> None:
    """
    Bind a channel to an agent. Reactivates the channel and steals it from any
    other agent it was previously bound to (a channel maps to exactly one agent).
    Keeps users.channel_ids / chan_titles JSON lists in sync.
    """
    if await get_user(user_id) is None:
        await upsert_user(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO channels (channel_id, user_id, chan_title, active, agent_id)
            VALUES (?,?,?,1,?)
            ON CONFLICT(channel_id, user_id) DO UPDATE SET
                chan_title=excluded.chan_title,
                active=1,
                agent_id=excluded.agent_id
            """,
            (channel_id, user_id, chan_title, agent_id),
        )
        # Steal from any other (user_id) binding of the same channel.
        await db.execute(
            "UPDATE channels SET agent_id=?, active=1 WHERE channel_id=?",
            (agent_id, channel_id),
        )
        await db.commit()

    user = await get_user(user_id)
    channel_ids: list = user.get("channel_ids") or []
    chan_titles: dict = user.get("chan_titles") or {}
    if channel_id not in channel_ids:
        channel_ids.append(channel_id)
    chan_titles[str(channel_id)] = chan_title
    await upsert_user(user_id, channel_ids=channel_ids, chan_titles=chan_titles)


async def remove_channel_from_agent(agent_id: int, channel_id: int) -> None:
    """Unbind a channel from an agent (soft-delete: active=0, agent_id=NULL)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM channels WHERE channel_id=? AND agent_id=?",
            (channel_id, agent_id),
        ) as cur:
            row = await cur.fetchone()
        await db.execute(
            "UPDATE channels SET active=0, agent_id=NULL "
            "WHERE channel_id=? AND agent_id=?",
            (channel_id, agent_id),
        )
        await db.commit()

    if not row:
        return
    user_id = row["user_id"]
    user = await get_user(user_id)
    if user is None:
        return
    channel_ids = [c for c in (user.get("channel_ids") or []) if c != channel_id]
    chan_titles = {k: v for k, v in (user.get("chan_titles") or {}).items()
                   if k != str(channel_id)}
    await upsert_user(user_id, channel_ids=channel_ids, chan_titles=chan_titles)


async def get_channels_for_agent(agent_id: int) -> list[dict]:
    """Return active channel rows bound to an agent."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE agent_id=? AND active=1 ORDER BY rowid ASC",
            (agent_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

async def log_post_stat(
    user_id: int,
    channel_id: int,
    response_ms: int,
    success: bool,
) -> None:
    """
    Record a single post-processing event in post_stats and
    bump the aggregate counter on the users row.
    """
    ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO post_stats (user_id, channel_id, ts, response_ms, success) "
            "VALUES (?,?,?,?,?)",
            (user_id, channel_id, ts, response_ms, int(success)),
        )
        field = "posts_processed" if success else "posts_failed"
        await db.execute(
            f"UPDATE users SET {field}={field}+1 WHERE user_id=?",
            (user_id,),
        )
        await db.commit()


async def get_stats_for_user(user_id: int) -> dict:
    """
    Return aggregated per-user statistics from post_stats:
      total, failed, avg_ms (successful posts only), last_ts.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                COUNT(*)                                        AS total,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)     AS failed,
                AVG(CASE WHEN success=1 THEN response_ms END)   AS avg_ms,
                MAX(ts)                                         AS last_ts
            FROM post_stats
            WHERE user_id=?
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "total":   row["total"] or 0,
                    "failed":  row["failed"] or 0,
                    "avg_ms":  round(row["avg_ms"] or 0),
                    "last_ts": row["last_ts"],
                }
    return {"total": 0, "failed": 0, "avg_ms": 0, "last_ts": None}


async def reset_stats_for_user(user_id: int) -> None:
    """Wipe per-user post_stats rows and zero the aggregate counters."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM post_stats WHERE user_id=?", (user_id,))
        await db.execute(
            "UPDATE users SET posts_processed=0, posts_failed=0 WHERE user_id=?",
            (user_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Per-provider credentials (provider_configs)
# ---------------------------------------------------------------------------

async def get_provider_config(user_id: int, provider: str) -> Optional[dict]:
    """Return saved {api_base, api_key, model_id} for a user+provider, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM provider_configs WHERE user_id=? AND provider=?",
            (user_id, provider),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_provider_config(user_id: int, provider: str, **kwargs) -> None:
    """Insert or update api_base/api_key/model_id for a user+provider."""
    allowed = {"api_base", "api_key", "model_id"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    existing = await get_provider_config(user_id, provider)
    async with aiosqlite.connect(DB_PATH) as db:
        if existing is None:
            cols = ["user_id", "provider"] + list(fields.keys())
            vals = [user_id, provider] + list(fields.values())
            placeholders = ",".join(["?"] * len(vals))
            await db.execute(
                f"INSERT INTO provider_configs ({','.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        elif fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            vals = list(fields.values()) + [user_id, provider]
            await db.execute(
                f"UPDATE provider_configs SET {sets} WHERE user_id=? AND provider=?",
                vals,
            )
        await db.commit()


async def get_provider_configs(user_id: int) -> dict[str, dict]:
    """Return {provider: {api_base, api_key, model_id}} for all saved providers."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM provider_configs WHERE user_id=?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
            return {r["provider"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Settings (global KV)
# ---------------------------------------------------------------------------

async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def delete_setting(key: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key=?", (key,))
        await db.commit()


# ---------------------------------------------------------------------------
# Admin / moderation
# ---------------------------------------------------------------------------

async def set_admin(user_id: int, flag: bool) -> None:
    await upsert_user(user_id, is_admin=int(flag))


async def set_banned(user_id: int, flag: bool) -> None:
    await upsert_user(user_id, is_banned=int(flag))


async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user and user.get("is_banned"))


async def list_users(limit: int = 50, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at ASC, user_id ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_user(r) for r in rows]


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def global_stats() -> dict:
    """Aggregate counters across all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) AS users, "
            "COALESCE(SUM(posts_processed),0) AS processed, "
            "COALESCE(SUM(posts_failed),0) AS failed FROM users"
        ) as cur:
            row = await cur.fetchone()
            return {
                "users": row["users"] or 0,
                "processed": row["processed"] or 0,
                "failed": row["failed"] or 0,
            }


# ---------------------------------------------------------------------------
# Request log (admin logs view)
# ---------------------------------------------------------------------------

async def log_request(
    user_id: Optional[int],
    channel_id: Optional[int],
    provider: str,
    model: str,
    ok: bool,
    response_ms: int,
    error: str = "",
) -> None:
    ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO request_log "
            "(user_id, channel_id, provider, model, ok, response_ms, error, ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, channel_id, provider, model, int(ok), response_ms, error, ts),
        )
        await db.commit()


async def recent_logs(limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM request_log ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
