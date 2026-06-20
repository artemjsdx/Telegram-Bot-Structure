"""
Central configuration, loaded from .env.
All other modules import their settings from here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DB_PATH: str = os.getenv("DB_PATH", "data/bot.db")
DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "ru")
SYSTEM_PROMPT_PATH: str = os.getenv(
    "SYSTEM_PROMPT_PATH", "system_prompt/telegram_formatting.txt"
)
PRESETS_DIR: str = os.getenv("PRESETS_DIR", "system_prompt/presets")


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS: set[int] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

# Bot owner / support contact. The @username is resolved live from this ID at
# render time (help screen) so it always reflects the owner's current handle.
OWNER_ID: int = int(os.getenv("OWNER_ID", "8149203573"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")
