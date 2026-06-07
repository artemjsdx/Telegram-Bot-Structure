import aiosqlite
import os
from typing import Optional
from config import DB_PATH


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                api_base    TEXT    DEFAULT '',
                api_key     TEXT    DEFAULT '',
                model_id    TEXT    DEFAULT '',
                user_prompt TEXT    DEFAULT '',
                sys_prompt  INTEGER DEFAULT 1,
                channel_id  INTEGER,
                chan_title  TEXT,
                setup_done  INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_user(user_id: int, **kwargs):
    user = await get_user(user_id)
    if user is None:
        fields = ["user_id"] + list(kwargs.keys())
        values = [user_id] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        cols = ",".join(fields)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})", values
            )
            await db.commit()
    else:
        if not kwargs:
            return
        sets = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE users SET {sets} WHERE user_id=?", values
            )
            await db.commit()


async def get_user_by_channel(channel_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE channel_id=?", (channel_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
