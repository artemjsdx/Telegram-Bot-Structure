"""
Idempotent migration script for FavoriteStructure v2.0.

Adds new columns to an existing SQLite DB and creates new tables.
Safe to run multiple times — checks existence before altering.
Creates a .bak snapshot before touching anything.

Usage:
    python -m db.migrate        (from project root)
    python bot/db/migrate.py    (direct)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Optional

import aiosqlite
from config import DB_PATH

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Columns to add to existing tables (idempotent)
# (table, column_name, column_definition)
# ---------------------------------------------------------------------------
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "channel_ids",      "TEXT    DEFAULT '[]'"),
    ("users", "chan_titles",      "TEXT    DEFAULT '{}'"),
    ("users", "preview_mode",     "INTEGER DEFAULT 0"),
    ("users", "provider",         "TEXT    DEFAULT 'favoriteapi'"),
    ("users", "posts_processed",  "INTEGER DEFAULT 0"),
    ("users", "posts_failed",     "INTEGER DEFAULT 0"),
    ("users", "lang",             "TEXT    DEFAULT 'ru'"),
    ("users", "is_admin",         "INTEGER DEFAULT 0"),
    ("users", "is_banned",        "INTEGER DEFAULT 0"),
    ("users", "active_channel_id", "INTEGER"),
    ("users", "created_at",       "INTEGER DEFAULT 0"),
    ("users", "username",         "TEXT    DEFAULT ''"),
    ("users", "first_name",       "TEXT    DEFAULT ''"),
    ("users", "last_seen",        "INTEGER DEFAULT 0"),
    ("users", "blocked",          "INTEGER DEFAULT 0"),
    ("users", "blocked_at",       "INTEGER DEFAULT 0"),
    ("channels", "agent_id",      "INTEGER"),
]

# ---------------------------------------------------------------------------
# New tables / indexes to create if missing
# ---------------------------------------------------------------------------
NEW_TABLE_SQL: list[str] = [
    """CREATE TABLE IF NOT EXISTS agents (
        agent_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        name        TEXT    DEFAULT '',
        provider    TEXT    DEFAULT 'favoriteapi',
        api_base    TEXT    DEFAULT '',
        api_key     TEXT    DEFAULT '',
        model_id    TEXT    DEFAULT '',
        user_prompt TEXT    DEFAULT '',
        sys_prompt  INTEGER DEFAULT 1,
        created_at  INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS channels (
        channel_id  INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        chan_title  TEXT    DEFAULT '',
        active      INTEGER DEFAULT 1,
        prompt      TEXT    DEFAULT '',
        provider    TEXT    DEFAULT 'favoriteapi',
        agent_id    INTEGER,
        PRIMARY KEY (channel_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS post_stats (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        ts          INTEGER NOT NULL,
        response_ms INTEGER DEFAULT 0,
        success     INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS provider_configs (
        user_id   INTEGER NOT NULL,
        provider  TEXT    NOT NULL,
        api_base  TEXT    DEFAULT '',
        api_key   TEXT    DEFAULT '',
        model_id  TEXT    DEFAULT '',
        PRIMARY KEY (user_id, provider)
    )""",
    """CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS request_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        channel_id  INTEGER,
        provider    TEXT,
        model       TEXT,
        ok          INTEGER DEFAULT 1,
        response_ms INTEGER DEFAULT 0,
        error       TEXT,
        ts          INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS user_presets (
        preset_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        name        TEXT    DEFAULT '',
        body        TEXT    DEFAULT '',
        created_at  INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_channels_user ON channels(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_channels_agent ON channels(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_agents_user ON agents(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_post_stats_user ON post_stats(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_post_stats_channel ON post_stats(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_post_stats_ts ON post_stats(ts)",
    "CREATE INDEX IF NOT EXISTS idx_provider_configs_user ON provider_configs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_request_log_ts ON request_log(ts)",
    "CREATE INDEX IF NOT EXISTS idx_user_presets_user ON user_presets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_users_blocked_at ON users(blocked_at)",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
        return {row[1] for row in rows}


async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cur:
        return await cur.fetchone() is not None


async def _migrate_old_channel_data(db: aiosqlite.Connection) -> None:
    """
    One-time migration: if users table still has the old 'channel_id'/'chan_title'
    single-channel columns, copy that data into:
      - channels table (proper rows)
      - users.channel_ids (JSON list)
      - users.chan_titles (JSON dict)
    """
    cols = await _get_columns(db, "users")
    if "channel_id" not in cols:
        return  # Already migrated or fresh install

    log.info("Found old single-channel schema — migrating data…")
    async with db.execute(
        "SELECT user_id, channel_id, chan_title FROM users WHERE channel_id IS NOT NULL"
    ) as cur:
        rows = await cur.fetchall()

    migrated = 0
    for user_id, channel_id, chan_title in rows:
        if not channel_id:
            continue
        chan_title = chan_title or ""

        # Insert into channels table (ignore if already there)
        await db.execute(
            """INSERT OR IGNORE INTO channels (channel_id, user_id, chan_title, active)
               VALUES (?,?,?,1)""",
            (channel_id, user_id, chan_title),
        )

        # Update JSON fields — only if they are still empty/default
        cids_json = json.dumps([channel_id])
        ctitles_json = json.dumps({str(channel_id): chan_title})
        await db.execute(
            """UPDATE users
               SET channel_ids=?, chan_titles=?
               WHERE user_id=?
                 AND (channel_ids IS NULL OR channel_ids='[]')""",
            (cids_json, ctitles_json, user_id),
        )
        migrated += 1

    log.info("Migrated %d users from old single-channel schema.", migrated)


async def _migrate_creds_to_provider_configs(db: aiosqlite.Connection) -> None:
    """
    One-time: copy each user's users.api_base/api_key/model_id into
    provider_configs(provider=users.provider or 'favoriteapi'), so per-provider
    credentials persist and switching providers no longer wipes them.
    Idempotent: INSERT OR IGNORE keeps any existing per-provider row untouched.
    """
    cols = await _get_columns(db, "users")
    if not {"api_key", "provider"} <= cols:
        return

    async with db.execute(
        "SELECT user_id, provider, api_base, api_key, model_id FROM users"
    ) as cur:
        rows = await cur.fetchall()

    copied = 0
    for user_id, provider, api_base, api_key, model_id in rows:
        if not (api_key or api_base or model_id):
            continue
        provider = provider or "favoriteapi"
        await db.execute(
            """INSERT OR IGNORE INTO provider_configs
               (user_id, provider, api_base, api_key, model_id)
               VALUES (?,?,?,?,?)""",
            (user_id, provider, api_base or "", api_key or "", model_id or ""),
        )
        copied += 1

    if copied:
        log.info("Seeded provider_configs from %d user rows.", copied)


async def _seed_created_at(db: aiosqlite.Connection) -> None:
    """Backfill created_at for rows that still have the 0 default."""
    if "created_at" not in await _get_columns(db, "users"):
        return
    await db.execute(
        "UPDATE users SET created_at=? WHERE created_at IS NULL OR created_at=0",
        (int(time.time()),),
    )


async def _migrate_users_to_agents(db: aiosqlite.Connection) -> None:
    """
    One-time: turn each configured user into a default agent ("Агент 1") and
    bind their existing channels to it.

    Credentials are resolved EXACTLY like core.ai_client.resolve_creds:
      provider = users.provider or 'favoriteapi'
      → provider_configs[user_id, provider] for base/key/model
      → else fall back to users.api_base/api_key/model_id
    Empty api_base is kept empty (runtime fills the provider default — avoids
    baking in rotating trycloudflare/openrouter URLs).

    Idempotent: only processes users that still have an unbound active channel,
    so a second run finds nothing to do and never creates a duplicate agent.
    """
    if not await _table_exists(db, "agents"):
        return
    if not await _table_exists(db, "channels"):
        return

    # Users who have at least one channel not yet bound to an agent.
    async with db.execute(
        """
        SELECT DISTINCT c.user_id
        FROM channels c
        JOIN users u ON u.user_id = c.user_id
        WHERE c.agent_id IS NULL AND u.setup_done=1
        """
    ) as cur:
        user_ids = [row[0] for row in await cur.fetchall()]

    if not user_ids:
        return

    now = int(time.time())
    created = 0
    for user_id in user_ids:
        # Load user row for provider + legacy creds.
        async with db.execute(
            "SELECT provider, api_base, api_key, model_id, user_prompt, sys_prompt "
            "FROM users WHERE user_id=?",
            (user_id,),
        ) as cur:
            u = await cur.fetchone()
        if not u:
            continue
        provider = u[0] or "favoriteapi"
        u_base, u_key, u_model = u[1] or "", u[2] or "", u[3] or ""
        user_prompt = u[4] or ""
        sys_prompt = u[5] if u[5] is not None else 1

        # Prefer per-provider creds (the real runtime source of truth).
        async with db.execute(
            "SELECT api_base, api_key, model_id FROM provider_configs "
            "WHERE user_id=? AND provider=?",
            (user_id, provider),
        ) as cur:
            pc = await cur.fetchone()
        if pc:
            api_base, api_key, model_id = pc[0] or "", pc[1] or "", pc[2] or ""
        else:
            api_base, api_key, model_id = u_base, u_key, u_model

        cur2 = await db.execute(
            """INSERT INTO agents
               (user_id, name, provider, api_base, api_key, model_id,
                user_prompt, sys_prompt, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user_id, "Агент 1", provider, api_base, api_key, model_id,
             user_prompt, int(sys_prompt), now),
        )
        agent_id = cur2.lastrowid
        await db.execute(
            "UPDATE channels SET agent_id=? WHERE user_id=? AND agent_id IS NULL",
            (agent_id, user_id),
        )
        created += 1

    if created:
        log.info("Created %d default agent(s) from existing users.", created)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_migrations() -> None:
    """
    Run all pending migrations against the live DB.
    Steps:
      1. Backup DB (db_path.bak)
      2. Add missing columns to existing tables
      3. Create new tables / indexes
      4. Migrate old single-channel data to new schema
    """
    if not os.path.exists(DB_PATH):
        log.info("DB not found at %s — nothing to migrate (init_db will create it).", DB_PATH)
        return

    # Backup
    bak = DB_PATH + ".bak"
    shutil.copy2(DB_PATH, bak)
    log.info("DB backed up → %s", bak)

    async with aiosqlite.connect(DB_PATH) as db:
        # Step 1: Add missing columns
        for table, col, col_def in COLUMN_MIGRATIONS:
            if not await _table_exists(db, table):
                log.debug("Table '%s' not found — skipping column '%s'.", table, col)
                continue
            existing = await _get_columns(db, table)
            if col not in existing:
                sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
                log.info("  %s", sql)
                await db.execute(sql)
            else:
                log.debug("  Column '%s.%s' already exists — skipped.", table, col)

        # Step 2: Create new tables / indexes
        for sql in NEW_TABLE_SQL:
            await db.execute(sql)

        # Step 3: Migrate old single-channel data
        await _migrate_old_channel_data(db)

        # Step 4: Seed per-provider credentials + created_at
        await _migrate_creds_to_provider_configs(db)
        await _seed_created_at(db)

        # Step 5: Turn configured users into default agents + bind channels
        await _migrate_users_to_agents(db)

        await db.commit()

    log.info("All migrations complete.")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    asyncio.run(run_migrations())
