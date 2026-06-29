"""
Telethon (MTProto) client manager for the autoposting userbot.

Sessions are stored as Telethon StringSessions in the DB (tg_accounts.session) —
no session files on disk. One TelegramClient per account is cached and reused by
the autopost worker. Login is a 3-step interactive flow driven by the bot
conversation: phone → code → optional 2FA password.

MTProto is also what lets us move media up to ~2 GB (Bot API caps downloads at
20 MB / uploads at 50 MB): the worker downloads/re-uploads big files through this
client when needed.

Telethon is imported defensively: if the dependency isn't installed (e.g. a failed
pip on deploy), the bot still runs — autoposting is simply unavailable and says so.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        FloodWaitError,
    )
    TELETHON_AVAILABLE = True
except Exception as e:  # noqa: BLE001
    TELETHON_AVAILABLE = False
    _IMPORT_ERR = str(e)
    logger.warning("Telethon unavailable — autoposting disabled: %s", e)


# account_id → connected TelegramClient (worker reuse)
_clients: dict[int, "TelegramClient"] = {}
# user_id → in-progress login state {client, phone, phone_code_hash, api_id, api_hash}
_pending: dict[int, dict] = {}


def available() -> bool:
    return TELETHON_AVAILABLE


def _new_client(session: str, api_id: int, api_hash: str) -> "TelegramClient":
    return TelegramClient(StringSession(session or None), int(api_id), api_hash)


# ───── interactive login (bot conversation) ─────
async def begin_login(user_id: int, api_id: int, api_hash: str, phone: str) -> str:
    """
    Step 1: connect and request an SMS/app login code. Returns a status:
      'code_sent'   — code requested, ask the user for it;
      'already'     — this session was somehow already authorized;
      'error:<msg>' — failure (bad api_id/hash/phone).
    """
    if not TELETHON_AVAILABLE:
        return "error:Telethon не установлен на сервере"
    await cancel_login(user_id)
    try:
        client = _new_client("", api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            _pending[user_id] = {"client": client, "phone": phone,
                                 "api_id": api_id, "api_hash": api_hash}
            return "already"
        sent = await client.send_code_request(phone)
        _pending[user_id] = {
            "client": client, "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
            "api_id": api_id, "api_hash": api_hash,
        }
        return "code_sent"
    except Exception as e:  # noqa: BLE001
        logger.warning("begin_login failed for user %s: %s", user_id, e)
        await cancel_login(user_id)
        return f"error:{e}"


async def confirm_code(user_id: int, code: str) -> str:
    """
    Step 2: sign in with the code. Returns:
      'ok'        — signed in, call finish_login to get the session;
      'need_2fa'  — account has a cloud password, ask for it;
      'error:<m>' — invalid/expired code or other failure.
    """
    st = _pending.get(user_id)
    if not st:
        return "error:сессия входа истекла, начните заново"
    client = st["client"]
    try:
        await client.sign_in(phone=st["phone"], code=code.strip(),
                             phone_code_hash=st.get("phone_code_hash"))
        return "ok"
    except SessionPasswordNeededError:
        return "need_2fa"
    except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
        return f"error:{e}"
    except Exception as e:  # noqa: BLE001
        logger.warning("confirm_code failed for user %s: %s", user_id, e)
        return f"error:{e}"


async def confirm_password(user_id: int, password: str) -> str:
    """Step 2b: sign in with the 2FA cloud password. Returns 'ok' or 'error:<m>'."""
    st = _pending.get(user_id)
    if not st:
        return "error:сессия входа истекла, начните заново"
    try:
        await st["client"].sign_in(password=password)
        return "ok"
    except Exception as e:  # noqa: BLE001
        logger.warning("confirm_password failed for user %s: %s", user_id, e)
        return f"error:{e}"


async def finish_login(user_id: int) -> dict | None:
    """
    After 'ok': read identity + serialized session, disconnect the temp client.
    Returns {session, nickname, api_id, api_hash, phone} or None.
    """
    st = _pending.pop(user_id, None)
    if not st:
        return None
    client = st["client"]
    try:
        me = await client.get_me()
        nickname = ("@" + me.username) if getattr(me, "username", None) else \
            (getattr(me, "first_name", None) or st["phone"])
        session = client.session.save()
        return {
            "session": session, "nickname": nickname,
            "api_id": st["api_id"], "api_hash": st["api_hash"], "phone": st["phone"],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("finish_login failed for user %s: %s", user_id, e)
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def cancel_login(user_id: int) -> None:
    st = _pending.pop(user_id, None)
    if st and st.get("client"):
        try:
            await st["client"].disconnect()
        except Exception:  # noqa: BLE001
            pass


# ───── worker clients (cached, long-lived) ─────
async def get_client(account: dict) -> "TelegramClient | None":
    """Return a connected client for an account dict, cached by account_id."""
    if not TELETHON_AVAILABLE:
        return None
    aid = account["account_id"]
    client = _clients.get(aid)
    if client is not None and client.is_connected():
        return client
    try:
        client = _new_client(account.get("session") or "",
                             account.get("api_id") or 0, account.get("api_hash") or "")
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("account %s not authorized", aid)
            await client.disconnect()
            return None
        _clients[aid] = client
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning("get_client failed for account %s: %s", aid, e)
        return None


async def drop_client(account_id: int) -> None:
    client = _clients.pop(account_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def disconnect_all() -> None:
    for aid in list(_clients):
        await drop_client(aid)
    for uid in list(_pending):
        await cancel_login(uid)
