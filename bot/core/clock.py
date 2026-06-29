"""
Current Moscow date/time as a single human line for the model's context.

Injected into EVERY rewrite/autopost call (always on, not a setting) so the model
always knows "today" and can judge how fresh a message, post, or news item is.
Moscow has been a fixed UTC+3 with no DST since 2014, so a fixed offset is both
correct and dependency-free (no tzdata needed).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

_MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_WEEKDAYS_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]
_MONTHS_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_WEEKDAYS_EN = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]


def msk_now() -> datetime:
    return datetime.now(MSK)


def current_time_line(lang: str = "ru") -> str:
    """One line, e.g. 'Текущие дата и время (МСК): 29 июня 2026 (воскресенье), 14:30:05.'"""
    now = msk_now()
    if lang == "en":
        return (
            f"Current date and time (Moscow, UTC+3): "
            f"{_WEEKDAYS_EN[now.weekday()]}, {now.day} {_MONTHS_EN[now.month - 1]} "
            f"{now.year}, {now:%H:%M:%S}. Use it to judge how current any dated "
            f"message, post, or news item is."
        )
    return (
        f"Текущие дата и время (Москва, МСК, UTC+3): "
        f"{now.day} {_MONTHS_RU[now.month - 1]} {now.year} года "
        f"({_WEEKDAYS_RU[now.weekday()]}), {now:%H:%M:%S}. Используй это, чтобы "
        f"оценивать актуальность дат сообщений, постов и новостей."
    )
