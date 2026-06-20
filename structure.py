"""
Thin entrypoint. Puts bot/ on sys.path so package-less imports
(`from config import ...`, `from handlers.x import ...`) resolve, then hands off
to bot/app.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot"))

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
