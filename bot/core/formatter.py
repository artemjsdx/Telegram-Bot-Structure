"""
System-prompt and preset loading.

get_system_prompt() returns the Telegram-formatting instructions.
list_presets()/get_preset() expose the .txt files under system_prompt/presets/.
Paths come from config; relative paths resolve against the project root.
"""
from __future__ import annotations

import os

from config import SYSTEM_PROMPT_PATH, PRESETS_DIR

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_ROOT, path)


def get_system_prompt() -> str:
    try:
        with open(_resolve(SYSTEM_PROMPT_PATH), "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def list_presets() -> list[str]:
    """Preset names (filenames without the .txt suffix), sorted."""
    d = _resolve(PRESETS_DIR)
    try:
        names = [f[:-4] for f in os.listdir(d) if f.endswith(".txt")]
    except FileNotFoundError:
        return []
    return sorted(names)


def get_preset(name: str) -> str:
    """Body of a preset by name, or '' if it does not exist."""
    safe = os.path.basename(name)  # guard against path traversal
    path = os.path.join(_resolve(PRESETS_DIR), f"{safe}.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
