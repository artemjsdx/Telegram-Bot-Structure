"""
Database schema for FavoriteStructure v2.0
Tables: users, agents, channels, post_stats, provider_configs, settings, request_log
"""
import os
import aiosqlite
from config import DB_PATH


CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY,
    api_base          TEXT    DEFAULT '',
    api_key           TEXT    DEFAULT '',
    model_id          TEXT    DEFAULT '',
    user_prompt       TEXT    DEFAULT '',
    sys_prompt        INTEGER DEFAULT 1,
    channel_ids       TEXT    DEFAULT '[]',
    chan_titles       TEXT    DEFAULT '{}',
    setup_done        INTEGER DEFAULT 0,
    preview_mode      INTEGER DEFAULT 0,
    provider          TEXT    DEFAULT 'favoriteapi',
    posts_processed   INTEGER DEFAULT 0,
    posts_failed      INTEGER DEFAULT 0,
    lang              TEXT    DEFAULT 'ru',
    is_admin          INTEGER DEFAULT 0,
    is_banned         INTEGER DEFAULT 0,
    active_channel_id INTEGER,
    created_at        INTEGER DEFAULT 0,
    username          TEXT    DEFAULT '',
    first_name        TEXT    DEFAULT '',
    last_seen         INTEGER DEFAULT 0,
    blocked           INTEGER DEFAULT 0,
    blocked_at        INTEGER DEFAULT 0
)
"""

CREATE_PROVIDER_CONFIGS = """
CREATE TABLE IF NOT EXISTS provider_configs (
    user_id   INTEGER NOT NULL,
    provider  TEXT    NOT NULL,
    api_base  TEXT    DEFAULT '',
    api_key   TEXT    DEFAULT '',
    model_id  TEXT    DEFAULT '',
    PRIMARY KEY (user_id, provider)
)
"""

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

CREATE_REQUEST_LOG = """
CREATE TABLE IF NOT EXISTS request_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    channel_id  INTEGER,
    provider    TEXT,
    model       TEXT,
    ok          INTEGER DEFAULT 1,
    response_ms INTEGER DEFAULT 0,
    error       TEXT,
    ts          INTEGER NOT NULL
)
"""

CREATE_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
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
)
"""

CREATE_CHANNELS = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    chan_title  TEXT    DEFAULT '',
    active      INTEGER DEFAULT 1,
    prompt      TEXT    DEFAULT '',
    provider    TEXT    DEFAULT 'favoriteapi',
    agent_id    INTEGER,
    PRIMARY KEY (channel_id, user_id)
)
"""

CREATE_POST_STATS = """
CREATE TABLE IF NOT EXISTS post_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    ts          INTEGER NOT NULL,
    response_ms INTEGER DEFAULT 0,
    success     INTEGER DEFAULT 1
)
"""

CREATE_USER_PRESETS = """
CREATE TABLE IF NOT EXISTS user_presets (
    preset_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT    DEFAULT '',
    body        TEXT    DEFAULT '',
    created_at  INTEGER DEFAULT 0
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_channels_user ON channels(user_id)",
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


async def create_tables(db: aiosqlite.Connection) -> None:
    """Create all tables and indexes. Safe to call on existing DB."""
    await db.execute(CREATE_USERS)
    await db.execute(CREATE_AGENTS)
    await db.execute(CREATE_CHANNELS)
    await db.execute(CREATE_POST_STATS)
    await db.execute(CREATE_PROVIDER_CONFIGS)
    await db.execute(CREATE_SETTINGS)
    await db.execute(CREATE_REQUEST_LOG)
    await db.execute(CREATE_USER_PRESETS)
    for idx in CREATE_INDEXES:
        await db.execute(idx)
    await db.commit()
