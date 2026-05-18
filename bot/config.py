import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DB_PATH: str = os.getenv("DB_PATH", "data/bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")
