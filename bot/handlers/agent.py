"""
Agents: the home screen and the creation wizard.

The main menu is now a list of the user's agents. Each agent is a fully
self-contained config (provider + key + model + prompt + sys-toggle) that can be
bound to one or more channels. Post routing (core/monitor.py) finds the agent
owning a channel and rewrites with that agent's creds.

Creation wizard (per-agent, never touches user-level creds):
  name → provider → [api_base if required] → key (verify + fetch models)
       → model (paginated, searchable) → prompt → sys-toggle → bind channel
The model picker uses the `amodel:` / `amodelpage:` namespace so it never clashes
with provider.py's global `model:` / `modelpage:` handlers.
"""
from __future__ import annotations

import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import DEFAULT_LANG
from constants import (
    A_NAME, A_PROVIDER, A_API_BASE, A_API_KEY, A_MODEL,
    A_PROMPT, A_SYS_TOGGLE, A_BIND, A_MODEL_SEARCH,
    PROVIDER_ORDER,
)
from core.ai_client import verify, fetch_models, resolve_creds_from_agent
from core.formatter import list_presets, get_preset
from core.queue import queue
from db.storage import (
    get_user, upsert_user,
    create_agent, get_agent, get_agents_for_user, update_agent, delete_agent,
    add_channel_to_agent, remove_channel_from_agent, get_channels_for_agent,
    create_user_preset, get_user_presets, get_user_preset, delete_user_preset,
    get_user_by_handle, create_preset_share, set_preset_share_status,
)
from telegram.error import Forbidden
from handlers.channel import verify_forwarded_channel
from handlers.menu import nav, is_admin, send_main_menu
from keyboards.factory import (
    agents_list_kb, agent_card_kb, agent_channels_kb, agent_provider_kb,
    model_kb, confirm_kb, home_btn, PROVIDER_LABELS,
    preset_lib_kb, preset_detail_kb, preset_suggest_kb, preset_collect_kb,
    preset_mode_kb, preset_share_confirm_kb, pshare_offer_kb,
)
from providers import get_provider
from texts import t

log = logging.getLogger(__name__)


def _lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("agent_lang", DEFAULT_LANG)


def _skip_btn(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(t(lang, "agent_skip_setup"), callback_data="agent:skip_setup")


def _skip_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_skip_btn(lang)]])


def _with_skip(kb: InlineKeyboardMarkup, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(kb.inline_keyboard) + [[_skip_btn(lang)]])


def _sys_kb(enabled: bool, lang: str) -> InlineKeyboardMarkup:
    # No skip-setup button here: this is the final wizard step (name/provider/key/
    # model/prompt are already entered), so "➡️ Next" finalises the agent. A skip
    # button at this point only throws all that work away — a footgun. Bail via
    # /cancel if needed.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            t(lang, "settings_sys_on") if enabled else t(lang, "settings_sys_off"),
            callback_data="agent:sys")],
        [InlineKeyboardButton("➡️ " + t(lang, "agent_next"), callback_data="agent:sysdone")],
    ])


def _active_models(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    """The model list the picker indexes into (filtered view if a search is active)."""
    view = context.user_data.get("agent_model_view")
    return view if view is not None else context.user_data.get("agent_models", [])


def _picker_kwargs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Model-picker keyboard params, context-aware for the create vs edit flow.

    Edit flow (``edit_agent_id`` set) → back to the card, no skip button.
    Create flow → back to the agents list, with a skip-setup button.
    """
    eid = context.user_data.get("edit_agent_id")
    if eid:
        return {"back_cb": f"agent:view:{eid}", "search_cb": "amodel:search", "skip_cb": None}
    return {"back_cb": "agent:list", "search_cb": "amodel:search", "skip_cb": "agent:skip_setup"}


def _skip_kb_or_none(context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Skip keyboard for create-flow text prompts; nothing in the edit flow."""
    return None if context.user_data.get("edit_agent_id") else _skip_kb(lang)


def _prompt_entry_kb(context: ContextTypes.DEFAULT_TYPE, lang: str) -> InlineKeyboardMarkup:
    """Keyboard shown on the 'enter prompt' screen: library + skip (create) or back-to-card (edit)."""
    rows = [[InlineKeyboardButton(t(lang, "preset_lib_btn"), callback_data="agent:plib")]]
    eid = context.user_data.get("edit_agent_id")
    if eid:
        rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"agent:view:{eid}")])
    else:
        rows.append([_skip_btn(lang)])
    return InlineKeyboardMarkup(rows)


# ───── Home screen (agents list) ─────
async def show_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    agents = await get_agents_for_user(user_id)
    text = t(lang, "agents_title") if agents else t(lang, "agents_empty")
    kb = agents_list_kb(agents, lang, is_admin(user, user_id))
    await nav(update, context, text, kb)


async def show_agent_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    await _render_card(update, context, aid, edit=True)


async def _render_card(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       aid: int, edit: bool) -> None:
    user = await get_user(update.effective_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    agent = await get_agent(aid)
    if not agent:
        await show_agents(update, context)
        return
    channels = await get_channels_for_agent(aid)
    chan_line = ", ".join(c.get("chan_title") or str(c["channel_id"]) for c in channels) \
        if channels else "—"
    prov_label = PROVIDER_LABELS.get(agent.get("provider"), agent.get("provider") or "—")
    # The prompt may itself contain HTML tags the user wants to USE (<b>, <code>,
    # <pre>…); escape it so they show as literal text instead of being rendered
    # (and breaking the blockquote layout). Truncate on the raw text, then escape,
    # so a cut never lands inside an entity.
    raw_prompt = agent.get("user_prompt") or "—"
    prompt_disp = html.escape(raw_prompt[:200])
    if len(raw_prompt) > 200:
        prompt_disp += "…"
    mode = agent.get("struct_mode") or "edit"
    react_fwd = bool(agent.get("react_forwarded", 0))
    mode_v = t(lang, "agent_mode_resend_v" if mode == "resend" else "agent_mode_edit_v")
    fwd_v = t(lang, "agent_fwd_on_v" if react_fwd else "agent_fwd_off_v")
    text = t(
        lang, "agent_card",
        name=html.escape(agent.get("name") or f"#{aid}"),
        provider=html.escape(prov_label),
        model=html.escape(agent.get("model_id") or "—"),
        prompt=prompt_disp,
        mode=mode_v,
        forwarded=fwd_v,
        channels=html.escape(chan_line),
    )
    kb = agent_card_kb(aid, bool(agent.get("sys_prompt", 1)), lang,
                       mode=mode, react_fwd=react_fwd)
    q = update.callback_query
    if edit and q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await nav(update, context, text, kb)


# ───── Wizard: step 1 — name ─────
async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data.clear()
    context.user_data["agent_lang"] = lang
    context.user_data["agent_sys"] = True
    # The origin may be the main-menu banner (photo/video), which has no text to
    # edit. Try an in-place edit, fall back to delete+resend (nav) like show().
    try:
        await q.edit_message_text(
            t(lang, "agent_ask_name"), parse_mode=ParseMode.HTML, reply_markup=_skip_kb(lang)
        )
    except Exception:
        await nav(update, context, t(lang, "agent_ask_name"), _skip_kb(lang))
    return A_NAME


async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    name = (update.message.text or "").strip()[:64]
    if not name:
        await update.message.reply_text(t(lang, "agent_ask_name"), reply_markup=_skip_kb(lang))
        return A_NAME
    context.user_data["agent_name"] = name
    await update.message.reply_text(
        t(lang, "agent_ask_provider"), parse_mode=ParseMode.HTML,
        reply_markup=_with_skip(agent_provider_kb(lang), lang),
    )
    return A_PROVIDER


# ───── Wizard: step 2 — provider ─────
async def on_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    provider = q.data.split(":")[2]
    context.user_data["agent_provider"] = provider
    prov = get_provider(provider)

    if provider == "freemodel":
        await q.message.reply_text(t(lang, "provider_freemodel_warn"))

    if prov.requires_api_base() and not prov.default_api_base():
        await q.edit_message_text(
            t(lang, "provider_enter_base"), parse_mode=ParseMode.HTML,
            reply_markup=_skip_kb(lang),
        )
        return A_API_BASE

    context.user_data["agent_base"] = prov.default_api_base()
    await q.edit_message_text(
        t(lang, "provider_enter_key"), parse_mode=ParseMode.HTML,
        reply_markup=_skip_kb(lang),
    )
    return A_API_KEY


async def on_api_base(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    url = (update.message.text or "").strip().rstrip("/")
    if not url.startswith("http"):
        await update.message.reply_text(
            t(lang, "provider_enter_base"), reply_markup=_skip_kb(lang)
        )
        return A_API_BASE
    context.user_data["agent_base"] = url
    await update.message.reply_text(
        t(lang, "provider_enter_key"), reply_markup=_skip_kb(lang)
    )
    return A_API_KEY


# ───── Wizard: step 3 — key (verify + fetch models) ─────
async def on_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    key = (update.message.text or "").strip()
    provider = context.user_data.get("agent_provider")
    if not provider:
        # Wizard state was wiped (e.g. a sibling edit/menu flow cleared the shared
        # user_data) while this create-conv still sat at A_API_KEY. Recover instead
        # of crash-looping on every message the user sends.
        context.user_data.clear()
        await show_agents(update, context)
        return ConversationHandler.END
    api_base = context.user_data.get("agent_base", "") or get_provider(provider).default_api_base()
    status = await update.message.reply_text(t(lang, "provider_verifying"))

    try:
        await verify(provider, api_base, key)
    except Exception as e:
        await status.edit_text(
            t(lang, "provider_key_fail", error=str(e)[:300]), reply_markup=_skip_kb(lang)
        )
        return A_API_KEY

    context.user_data["agent_key"] = key
    context.user_data["agent_base"] = api_base
    try:
        models = await fetch_models(provider, api_base, key)
    except Exception:
        models = []
    if not models:
        models = ["default"]
    context.user_data["agent_models"] = models
    context.user_data["agent_model_view"] = None

    await status.edit_text(
        t(lang, "provider_key_ok") + "\n\n" + t(lang, "provider_choose_model"),
        reply_markup=model_kb(
            models, page=0, lang=lang,
            sel_prefix="amodel", page_prefix="amodelpage",
            **_picker_kwargs(context),
        ),
    )
    return A_MODEL


# ───── Wizard: step 4 — model picker (paginated + searchable) ─────
async def on_model_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    page = int(q.data.split(":")[1])
    await q.edit_message_reply_markup(
        model_kb(
            _active_models(context), page=page, lang=lang,
            sel_prefix="amodel", page_prefix="amodelpage",
            **_picker_kwargs(context),
        )
    )
    return A_MODEL


async def on_model_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    await q.edit_message_text(
        t(lang, "model_search_prompt"), parse_mode=ParseMode.HTML,
        reply_markup=_skip_kb_or_none(context, lang),
    )
    return A_MODEL_SEARCH


async def on_model_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    query = (update.message.text or "").strip().lower()
    all_models = context.user_data.get("agent_models", [])
    if query:
        filtered = [m for m in all_models if query in m.lower()]
        context.user_data["agent_model_view"] = filtered
    else:
        context.user_data["agent_model_view"] = None
        filtered = all_models
    if not filtered:
        await update.message.reply_text(
            t(lang, "model_search_none"),
            reply_markup=model_kb(
                all_models, page=0, lang=lang,
                sel_prefix="amodel", page_prefix="amodelpage",
                **_picker_kwargs(context),
            ),
        )
        context.user_data["agent_model_view"] = None
        return A_MODEL
    await update.message.reply_text(
        t(lang, "provider_choose_model"),
        reply_markup=model_kb(
            filtered, page=0, lang=lang,
            sel_prefix="amodel", page_prefix="amodelpage",
            **_picker_kwargs(context),
        ),
    )
    return A_MODEL


async def on_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    idx = int(q.data.split(":")[1])
    models = _active_models(context)
    model = models[idx] if 0 <= idx < len(models) else ""
    context.user_data["agent_model"] = model
    context.user_data["agent_model_view"] = None
    await q.edit_message_text(
        t(lang, "provider_model_set", model=model) + "\n\n" + t(lang, "prompt_enter"),
        parse_mode=ParseMode.HTML, reply_markup=_prompt_entry_kb(context, lang),
    )
    return A_PROMPT


# ───── Wizard: step 5 — prompt ─────
async def on_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # A preset sub-flow (create/save preset) may own this text input.
    routed = await _plib_text(update, context)
    if routed is not None:
        return routed
    lang = _lang(context)
    context.user_data["agent_prompt"] = (update.message.text or "").strip()
    await update.message.reply_text(
        t(lang, "agent_sys_title"), parse_mode=ParseMode.HTML,
        reply_markup=_sys_kb(context.user_data.get("agent_sys", True), lang),
    )
    return A_SYS_TOGGLE


# ───── Wizard: step 6 — sys-toggle ─────
async def on_sys_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data["agent_sys"] = not context.user_data.get("agent_sys", True)
    await q.edit_message_reply_markup(_sys_kb(context.user_data["agent_sys"], lang))
    return A_SYS_TOGGLE


async def on_sys_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist the agent, then prompt for the (optional) channel binding."""
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    ud = context.user_data
    aid = await create_agent(
        q.from_user.id,
        name=ud.get("agent_name", ""),
        provider=ud.get("agent_provider", "favoriteapi"),
        api_base=ud.get("agent_base", ""),
        api_key=ud.get("agent_key", ""),
        model_id=ud.get("agent_model", ""),
        user_prompt=ud.get("agent_prompt", ""),
        sys_prompt=1 if ud.get("agent_sys", True) else 0,
    )
    ud["agent_id"] = aid
    if not (await get_user(q.from_user.id) or {}).get("setup_done"):
        await upsert_user(q.from_user.id, setup_done=1)
    await q.edit_message_text(
        t(lang, "agent_bind_howto"), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "agent_bind_skip"), callback_data="agent:bind_skip")
        ]]),
    )
    return A_BIND


# ───── Wizard: step 7 — bind channel (final, skippable) ─────
async def on_bind_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    lang = _lang(context)
    aid = context.user_data.get("agent_id")
    if not aid:
        return ConversationHandler.END

    # Guard against binding to an agent that no longer exists (stale id in the
    # shared user_data). Otherwise the channel silently attaches to a ghost agent
    # and never shows up — looking like the binding "disappeared".
    if not await get_agent(aid):
        context.user_data.clear()
        await msg.reply_html(
            t(lang, "agent_gone"),
            reply_markup=InlineKeyboardMarkup([[home_btn(lang)]]),
        )
        return ConversationHandler.END

    result = await verify_forwarded_channel(msg, context.bot)
    if result is None:
        await msg.reply_text(t(lang, "channel_not_forwarded"))
        return A_BIND
    cid, title = result

    await add_channel_to_agent(aid, msg.from_user.id, cid, chan_title=title)
    user = await get_user(msg.from_user.id)
    if not (user or {}).get("active_channel_id"):
        await upsert_user(msg.from_user.id, active_channel_id=cid)

    context.user_data.clear()
    await msg.reply_html(
        t(lang, "agent_ready", title=title),
        reply_markup=InlineKeyboardMarkup([[home_btn(lang)]]),
    )
    return ConversationHandler.END


async def on_bind_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data.clear()
    await q.edit_message_text(
        t(lang, "agent_ready_nochan"), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[home_btn(lang)]]),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/cancel command — always arrives as a message."""
    lang = _lang(context)
    context.user_data.clear()
    await update.message.reply_text(t(lang, "cancelled"))
    return ConversationHandler.END


async def cancel_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back-to-list button inside a wizard: end the conversation, show the list."""
    context.user_data.clear()
    await show_agents(update, context)
    return ConversationHandler.END


async def skip_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip-setup button on any create-wizard step: abandon it, no agent created."""
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    await show_agents(update, context)
    return ConversationHandler.END


async def cancel_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Home button inside a wizard: end the conversation, show the main menu."""
    context.user_data.clear()
    await send_main_menu(update, context)
    return ConversationHandler.END


async def cancel_to_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back button inside an edit picker: end the conversation, show the agent card."""
    context.user_data.clear()
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    await _render_card(update, context, aid, edit=True)
    return ConversationHandler.END


# ───── Agent card edits ─────
async def on_edit_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data["edit_agent_id"] = aid
    rows = [[InlineKeyboardButton(PROVIDER_LABELS.get(p, p), callback_data=f"agent:setprov:{p}:{aid}")]
            for p in PROVIDER_ORDER]
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"agent:view:{aid}")])
    await q.edit_message_text(
        t(lang, "agent_ask_provider"), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def on_set_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    provider, aid = parts[2], int(parts[3])
    base = get_provider(provider).default_api_base()
    await update_agent(aid, provider=provider, api_base=base)
    await _render_card(update, context, aid, edit=True)


async def on_toggle_sys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    agent = await get_agent(aid)
    if agent:
        await update_agent(aid, sys_prompt=0 if agent.get("sys_prompt", 1) else 1)
    await _render_card(update, context, aid, edit=True)


async def on_toggle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Flip the agent's structuring mode between edit-in-place and resend."""
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    agent = await get_agent(aid)
    if agent:
        new_mode = "edit" if (agent.get("struct_mode") or "edit") == "resend" else "resend"
        await update_agent(aid, struct_mode=new_mode)
    await _render_card(update, context, aid, edit=True)


async def on_toggle_fwd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle whether the agent reacts to forwarded posts (always via resend)."""
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    agent = await get_agent(aid)
    if agent:
        await update_agent(aid, react_forwarded=0 if agent.get("react_forwarded", 0) else 1)
    await _render_card(update, context, aid, edit=True)


# ───── Agent channels submenu ─────
async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    channels = await get_channels_for_agent(aid)
    text = t(lang, "agent_channels_title") if channels else t(lang, "agent_channels_empty")
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=agent_channels_kb(aid, channels, lang),
    )


async def on_del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    cid, aid = int(parts[2]), int(parts[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    await remove_channel_from_agent(aid, cid)
    channels = await get_channels_for_agent(aid)
    text = t(lang, "agent_channels_title") if channels else t(lang, "agent_channels_empty")
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=agent_channels_kb(aid, channels, lang),
    )


# ───── Bind a channel to an EXISTING agent (from its channels submenu) ─────
async def addchan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """➕ «Привязать канал» on the channels submenu → ask for a forwarded post."""
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data["addchan_agent_id"] = aid
    context.user_data["agent_lang"] = lang
    await q.edit_message_text(
        t(lang, "agent_addchan_howto"), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"agent:chans:{aid}")
        ]]),
    )
    return A_BIND


async def addchan_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A forwarded post arrived → verify the channel and bind it to the agent."""
    msg = update.message
    lang = _lang(context)
    aid = context.user_data.get("addchan_agent_id")
    if not aid:
        return ConversationHandler.END

    # The agent may have been deleted while we waited for the forward.
    if not await get_agent(aid):
        context.user_data.pop("addchan_agent_id", None)
        await msg.reply_html(
            t(lang, "agent_gone"),
            reply_markup=InlineKeyboardMarkup([[home_btn(lang)]]),
        )
        return ConversationHandler.END

    result = await verify_forwarded_channel(msg, context.bot)
    if result is None:
        await msg.reply_text(t(lang, "channel_not_forwarded"))
        return A_BIND
    cid, title = result

    await add_channel_to_agent(aid, msg.from_user.id, cid, chan_title=title)
    user = await get_user(msg.from_user.id)
    if not (user or {}).get("active_channel_id"):
        await upsert_user(msg.from_user.id, active_channel_id=cid)

    context.user_data.pop("addchan_agent_id", None)
    channels = await get_channels_for_agent(aid)
    await msg.reply_text(
        t(lang, "agent_chan_added", title=html.escape(title)),
        parse_mode=ParseMode.HTML,
        reply_markup=agent_channels_kb(aid, channels, lang),
    )
    return ConversationHandler.END


async def addchan_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back button while waiting for a forward: end and re-show the channels submenu."""
    context.user_data.pop("addchan_agent_id", None)
    await show_channels(update, context)
    return ConversationHandler.END


# ───── Agent deletion (confirm) ─────
async def on_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    agent = await get_agent(aid)
    name = (agent or {}).get("name") or f"#{aid}"
    await q.edit_message_text(
        t(lang, "agent_confirm_delete", name=name),
        reply_markup=confirm_kb(f"agent:del_yes:{aid}", f"agent:view:{aid}", lang),
    )


async def on_delete_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[2])
    await delete_agent(aid)
    await show_agents(update, context)


# ───── Edit text-input flows (name / key / prompt) ─────
async def ask_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data["edit_agent_id"] = aid
    context.user_data["agent_lang"] = lang
    await q.edit_message_text(t(lang, "agent_ask_name"), parse_mode=ParseMode.HTML)
    return A_NAME


async def edit_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    aid = context.user_data.get("edit_agent_id")
    name = (update.message.text or "").strip()[:64]
    if aid and name:
        await update_agent(aid, name=name)
    context.user_data.clear()
    await _render_card(update, context, aid, edit=False)
    return ConversationHandler.END


async def ask_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data["edit_agent_id"] = aid
    context.user_data["agent_lang"] = lang
    await q.edit_message_text(
        t(lang, "prompt_enter"), parse_mode=ParseMode.HTML,
        reply_markup=_prompt_entry_kb(context, lang),
    )
    return A_PROMPT


async def edit_prompt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # A preset sub-flow (create/save preset) may own this text input.
    routed = await _plib_text(update, context)
    if routed is not None:
        return routed
    aid = context.user_data.get("edit_agent_id")
    if aid:
        await update_agent(aid, user_prompt=(update.message.text or "").strip())
    context.user_data.clear()
    await _render_card(update, context, aid, edit=False)
    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════
# Preset library
#
# Reachable from any prompt-entry screen (create wizard step 5 + edit-prompt).
# The library merges the user's own presets (⭐ favorites, on top, deletable)
# with the global read-only ones (📄). From here the user can also:
#   • ➕ create their own preset by hand (name → body),
#   • 🔮 forward a post and let the AI build a preset from its structure,
#     formatting and tone.
# Everything lives inside the A_PROMPT state — no new conversation states.
# Text typed in a sub-flow is routed by the `plib_mode` flag (see _plib_text);
# a forwarded post is caught by on_preset_forward (registered BEFORE the text
# handler). Scratch state kept in user_data: preset_items / preset_labels /
# preset_page / preset_sel_body / preset_suggested / plib_mode / plib_new_name.
# ═════════════════════════════════════════════════════════════════════════

# HTML tags the bot itself speaks — the AI is shown forwarded posts marked up
# with exactly these so it understands fonts/formatting, not just structure.
_BOT_HTML_TAGS = "<b> <i> <u> <s> <tg-spoiler> <code> <a> <blockquote>"


def _post_html(msg) -> str:
    """
    Render a forwarded post to HTML using the same tag vocabulary the bot uses,
    so the AI sees the fonts/formatting. PTB emits spoilers as
    <span class="tg-spoiler">…</span>; normalize that to <tg-spoiler>.
    """
    try:
        h = msg.text_html or msg.caption_html or ""
    except Exception:  # noqa: BLE001 — be defensive about odd entities
        h = msg.text or msg.caption or ""
    if not h:
        return ""
    return h.replace('<span class="tg-spoiler">', "<tg-spoiler>").replace("</span>", "</tg-spoiler>")


def _suggest_messages(posts: list[str], char_mode: str = "unified") -> list[dict]:
    """
    Build the meta-prompt that turns forwarded posts of the SAME channel into a
    reusable, TOPIC-AGNOSTIC preset. One axis shapes the instruction:
      char_mode: "unified"   → one common form for every post;
                 "scenarios" → several IF-THEN scenarios + a default fallback.
    The preset is always written from scratch. Several samples let the model infer
    the channel's real form, not one quirk.
    """
    budget = 9000 // max(1, len(posts))
    blocks = []
    for i, p in enumerate(posts, 1):
        blocks.append(
            f"[ПОСТ-ОБРАЗЕЦ #{i} С HTML-ФОРМАТИРОВАНИЕМ]\n{p[:budget]}\n[/ПОСТ-ОБРАЗЕЦ #{i}]"
        )
    samples = "\n\n".join(blocks)
    n = len(posts)

    head = (
        f"Ты — инженер промптов. Ниже даны {n} пост(ов) ОДНОГО Telegram-канала вместе с их "
        "исходными HTML-тегами форматирования. Это РАЗНЫЕ посты одного автора. На их основе "
        "составь ПЕРЕИСПОЛЬЗУЕМЫЙ пресет — инструкцию на русском языке, по которой другая "
        "нейросеть будет переписывать ЛЮБЫЕ будущие посты канала.\n\n"
    )

    if char_mode == "scenarios":
        task = (
            "🎬 РЕЖИМ «СЦЕНАРИИ». Образцы различаются по ТИПУ подачи (например: новость-"
            "уведомление, спокойное рассуждение, рекламный пост, личное мнение, анонс и т.п.). "
            "НЕ своди их к одной общей форме. Вместо этого опиши НЕСКОЛЬКО сценариев оформления — "
            "по одному на каждый характерный тип поста, который видно в образцах.\n"
            "Сформулируй пресет так: сначала инструкция «определи, к какому типу относится пост», "
            "затем явные правила вида «ЕСЛИ пост — <тип подачи>, ТО оформи так: <структура, "
            "форматирование, тон>», и к каждому сценарию — короткий пример оформления.\n"
            "ОБЯЗАТЕЛЬНО добавь ДЕФОЛТНЫЙ сценарий «по умолчанию»: как оформлять пост, если он не "
            "подходит ни под один из явных типов. Сценарии выделяй по ФОРМЕ подачи, а не по теме.\n\n"
        )
    else:
        task = (
            "🎭 РЕЖИМ «ЕДИНЫЙ ХАРАКТЕР». Выяви по образцам ОДНУ общую, повторяющуюся форму подачи "
            "(а не особенности одного поста) и опиши её как единый цельный стиль, одинаково "
            "применимый ко всем будущим постам канала. Не дроби на сценарии.\n\n"
        )

    guard = (
        "⚠️ КРИТИЧЕСКИ ВАЖНО (тема): канал публикует посты на САМЫЕ РАЗНЫЕ темы (крипта, мемы, "
        "личное мнение, новости и т.п.). Образцы показывают ФОРМУ, а не тему. Пресет должен "
        "описывать ТОЛЬКО форму подачи и НЕ привязываться к тематике: НЕ упоминай конкретные "
        "темы образцов, НЕ навязывай термины или примеры из них. Стиль обязан одинаково хорошо "
        "подходить и для мема, и для аналитики, и для личного поста на любую тему.\n\n"
        "⚠️ КРИТИЧЕСКИ ВАЖНО (естественность): пиши по-человечески, как живой автор. В сам "
        "пресет ОБЯЗАТЕЛЬНО включи требование переписывать естественно и сохранять авторский "
        "голос, а также ЯВНЫЙ ЗАПРЕТ на «нейросетевой» налёт: НЕ добавлять пафосные/кричащие "
        "заголовки, искусственные вступления и драматичные концовки (типа «врываюсь в работу», "
        "«не теряя ни секунды»), НЕ нагнетать, НЕ вставлять эмодзи, восклицания и обороты, "
        "которых не было в оригинале. Не выдумывай факты, не преувеличивай, не меняй смысл — "
        "только форма и подача. Если образцы написаны спокойно и просто — пресет должен "
        "сохранять эту спокойную простоту, а не «накручивать» энергию.\n\n"
        "Разбери и опиши именно ФОРМУ:\n"
        "1. СТРУКТУРА: как организован пост — заголовок (если он вообще есть), абзацы, списки, "
        "разделители, эмодзи-маркеры, типичная длина, начало и концовка, призывы к действию.\n"
        f"2. ФОРМАТИРОВАНИЕ/ШРИФТЫ: какие из тегов {_BOT_HTML_TAGS} реально используются и ГДЕ "
        "именно. Указывай только те приёмы, что действительно встречаются в образцах. Эти теги "
        "поддерживает бот, перечисляй их в инструкции.\n"
        "2а. ССЫЛКИ: встречаются ли в образцах гиперссылки <a href> и КАК автор их оформляет — "
        "на что вешает ссылку (отдельное слово, фраза, целое предложение или одна буква вроде "
        "«тут»/«здесь»), и комбинирует ли ссылку со шрифтами (например ссылка жирным или курсивом). "
        "Если в образцах есть такой приём — опиши его в пресете как правило (без конкретных URL: "
        "сами адреса бери только из переписываемого поста, не выдумывай).\n"
        "3. ХАРАКТЕР/ТОН: реальный голос и настроение автора (спокойный/деловой/дружеский/"
        "ироничный и т.д.), плотность эмодзи, манера обращения к читателю — без преувеличений.\n\n"
    )

    tail = (
        "Выведи ТОЛЬКО текст пресета-инструкции, без вступлений, пояснений и без блоков кода. "
        "Это должна быть прямая инструкция, которую можно сразу отдать модели-переписчику — про "
        "ФОРМУ, конкретная и применимая к ЛЮБОЙ теме.\n\n"
    )

    return [{"role": "user", "content": head + task + guard + tail + samples}]


async def _resolve_creds_for_flow(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """
    Credentials for the AI suggestion call, resolved from the active flow:
      edit flow (`edit_agent_id`) → the agent's own creds from the DB,
      create flow → the wizard's in-progress creds from user_data.
    Returns {provider, api_base, api_key, model} or None if unavailable.
    """
    eid = context.user_data.get("edit_agent_id")
    if eid:
        agent = await get_agent(eid)
        return resolve_creds_from_agent(agent) if agent else None
    provider = context.user_data.get("agent_provider")
    if not provider:
        return None
    base = context.user_data.get("agent_base") or get_provider(provider).default_api_base()
    return {
        "provider": provider,
        "api_base": base,
        "api_key": context.user_data.get("agent_key", ""),
        "model": context.user_data.get("agent_model", ""),
    }


async def _build_preset_items(context: ContextTypes.DEFAULT_TYPE,
                              user_id: int, lang: str) -> list[str]:
    """
    Merge the user's presets (⭐, newest first) with the global ones (📄) into a
    single indexed list. Caches the items + labels in user_data and returns the
    button labels for preset_lib_kb.
    """
    items: list[dict] = []
    labels: list[str] = []
    for p in await get_user_presets(user_id):
        items.append({"kind": "user", "id": p["preset_id"], "name": p["name"], "body": p["body"]})
        labels.append(f"⭐ {p['name']}")
    for name in list_presets():
        items.append({"kind": "global", "name": name})
        labels.append(f"📄 {name}")
    context.user_data["preset_items"] = items
    context.user_data["preset_labels"] = labels
    return labels


def _library_kb(labels: list[str], page: int, lang: str) -> InlineKeyboardMarkup:
    return preset_lib_kb(
        labels, page, lang, back_cb="apreset:exit",
        create_cb="apreset:new", fwd_cb="apreset:fwd",
    )


async def _render_library(q, context: ContextTypes.DEFAULT_TYPE, lang: str, page: int = 0) -> int:
    """Rebuild + show the library listing by editing `q`'s message. Does NOT answer `q`."""
    labels = await _build_preset_items(context, q.from_user.id, lang)
    context.user_data["preset_page"] = page
    await q.edit_message_text(
        t(lang, "preset_lib_title"), parse_mode=ParseMode.HTML,
        reply_markup=_library_kb(labels, page, lang),
    )
    return A_PROMPT


async def _apply_body(update: Update, context: ContextTypes.DEFAULT_TYPE, body: str) -> int:
    """
    Apply a prompt body to the agent. Works for both callback and message
    updates (the latter is used by the 'save & apply' text step).
      edit flow → persist on the agent, show its card, END.
      create flow → stash agent_prompt, advance to the sys-toggle step.
    """
    lang = _lang(context)
    q = update.callback_query
    eid = context.user_data.get("edit_agent_id")
    if eid:
        await update_agent(eid, user_prompt=body)
        context.user_data.clear()
        await _render_card(update, context, eid, edit=bool(q))
        return ConversationHandler.END
    context.user_data["agent_prompt"] = body
    for k in ("preset_items", "preset_labels", "preset_sel_body",
              "preset_suggested", "plib_mode", "plib_new_name", "preset_page",
              "preset_mode_char", "preset_fwd_posts", "preset_fwd_msg"):
        context.user_data.pop(k, None)
    text = t(lang, "agent_sys_title")
    kb = _sys_kb(context.user_data.get("agent_sys", True), lang)
    if q:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return A_SYS_TOGGLE


# ───── Library navigation ─────
async def open_preset_lib(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data.pop("plib_mode", None)
    context.user_data["preset_page"] = 0
    labels = await _build_preset_items(context, q.from_user.id, lang)
    await q.edit_message_text(
        t(lang, "preset_lib_title"), parse_mode=ParseMode.HTML,
        reply_markup=_library_kb(labels, 0, lang),
    )
    return A_PROMPT


async def preset_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    page = int(q.data.split(":")[1])
    context.user_data["preset_page"] = page
    labels = context.user_data.get("preset_labels")
    if labels is None:
        labels = await _build_preset_items(context, q.from_user.id, lang)
    await q.edit_message_reply_markup(_library_kb(labels, page, lang))
    return A_PROMPT


async def preset_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    idx = int(q.data.split(":")[1])
    items = context.user_data.get("preset_items") or []
    if not (0 <= idx < len(items)):
        return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))
    item = items[idx]
    if item["kind"] == "user":
        name, body = item["name"], item["body"]
        delete_cb = f"apreset:del:{item['id']}"
    else:
        name = item["name"]
        body = get_preset(name)
        delete_cb = None
    context.user_data["preset_sel_body"] = body
    context.user_data["preset_sel_name"] = name
    disp = html.escape(body)
    if len(disp) > 3500:
        disp = disp[:3500] + "…"
    await q.edit_message_text(
        t(lang, "preset_detail", name=html.escape(name), body=disp),
        parse_mode=ParseMode.HTML,
        reply_markup=preset_detail_kb(
            lang, "apreset:apply", "apreset:back", delete_cb, share_cb="apreset:share"),
    )
    return A_PROMPT


async def preset_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back to the (freshly rebuilt) library listing."""
    q = update.callback_query
    await q.answer()
    return await _render_library(q, context, _lang(context), context.user_data.get("preset_page", 0))


async def preset_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Leave the library, back to the prompt-entry screen (create or edit flow)."""
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data.pop("plib_mode", None)
    await q.edit_message_text(
        t(lang, "prompt_enter"), parse_mode=ParseMode.HTML,
        reply_markup=_prompt_entry_kb(context, lang),
    )
    return A_PROMPT


async def preset_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = _lang(context)
    await q.answer(t(lang, "prompt_preset_applied"))
    body = context.user_data.get("preset_sel_body", "")
    return await _apply_body(update, context, body)


# ───── Share a preset with another bot member ─────
def _who_label(u: dict) -> str:
    """A readable handle for a recipient: @username → name → numeric id."""
    if u.get("username"):
        return "@" + u["username"]
    if u.get("first_name"):
        return html.escape(u["first_name"])
    return str(u.get("user_id"))


def _share_back_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        t(lang, "pshare_back_btn"), callback_data="apreset:back")]])


async def preset_share_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """📨 Share on a preset detail → ask for the recipient's id/@username."""
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    if not context.user_data.get("preset_sel_body"):
        return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))
    context.user_data["plib_mode"] = "share_lookup"
    name = context.user_data.get("preset_sel_name", "")
    await q.edit_message_text(
        t(lang, "preset_share_ask", name=html.escape(name)),
        parse_mode=ParseMode.HTML, reply_markup=_share_back_kb(lang),
    )
    return A_PROMPT


async def preset_share_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """◀️ on the confirm screen → back to the recipient lookup."""
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data["plib_mode"] = "share_lookup"
    name = context.user_data.get("preset_sel_name", "")
    await q.edit_message_text(
        t(lang, "preset_share_ask", name=html.escape(name)),
        parse_mode=ParseMode.HTML, reply_markup=_share_back_kb(lang),
    )
    return A_PROMPT


async def preset_share_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """❌ Cancel the share flow → end the conversation, back to the main menu."""
    context.user_data.clear()
    await send_main_menu(update, context)
    return ConversationHandler.END


async def preset_share_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """📤 Confirm → record the offer and notify the recipient."""
    q = update.callback_query
    lang = _lang(context)
    to_user = context.user_data.get("share_to")
    name = context.user_data.get("preset_sel_name", "")
    body = context.user_data.get("preset_sel_body", "")
    if not to_user or not body:
        await q.answer(t(lang, "pshare_stale"), show_alert=True)
        return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))
    await q.answer()
    sender = await get_user(q.from_user.id)
    sender_label = _who_label(sender) if sender else str(q.from_user.id)
    recipient = await get_user(to_user)
    who = _who_label(recipient) if recipient else str(to_user)
    rlang = context.user_data.get("share_to_lang", DEFAULT_LANG)
    share_id = await create_preset_share(q.from_user.id, to_user, name, body)
    try:
        await context.bot.send_message(
            chat_id=to_user,
            text=t(rlang, "preset_share_recv", sender=sender_label, name=html.escape(name)),
            parse_mode=ParseMode.HTML,
            reply_markup=pshare_offer_kb(share_id, rlang),
        )
    except Forbidden:
        await set_preset_share_status(share_id, "failed")
        await q.edit_message_text(
            t(lang, "preset_share_fail"), parse_mode=ParseMode.HTML,
            reply_markup=_share_back_kb(lang),
        )
        return A_PROMPT
    for k in ("share_to", "share_to_lang", "plib_mode"):
        context.user_data.pop(k, None)
    await q.edit_message_text(
        t(lang, "preset_share_sent", name=html.escape(name), who=who),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            t(lang, "preset_back"), callback_data="apreset:back")]]),
    )
    return A_PROMPT


# ───── Create own preset (name → body) ─────
async def preset_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data["plib_mode"] = "new_name"
    await q.edit_message_text(t(lang, "preset_new_name"), parse_mode=ParseMode.HTML)
    return A_PROMPT


# ───── Delete own preset (confirm) ─────
async def preset_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    pid = int(q.data.split(":")[2])
    p = await get_user_preset(pid)
    if not p:
        return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))
    await q.edit_message_text(
        t(lang, "preset_delete_confirm", name=html.escape(p["name"])),
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb(f"apreset:delyes:{pid}", "apreset:back", lang),
    )
    return A_PROMPT


async def preset_delete_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = _lang(context)
    await q.answer(t(lang, "preset_deleted"))
    pid = int(q.data.split(":")[2])
    await delete_user_preset(pid)
    return await _render_library(q, context, lang, 0)


# ───── AI preset suggestion from forwarded posts ─────
# The user can forward up to PRESET_FWD_MAX posts (one at a time or several at
# once); each is buffered in user_data["preset_fwd_posts"]. A single live summary
# message (preset_fwd_msg) tracks the count + offers ⚡️ generate / ✖️ cancel.
# Feeding several real posts of the same channel lets the model infer the COMMON
# form instead of over-fitting one sample.
PRESET_FWD_MAX = 20


async def _show_collect_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                                lang: str, capped: bool = False) -> None:
    """(Re)place the single collection-summary message at the bottom of the chat."""
    posts = context.user_data.get("preset_fwd_posts", [])
    n = len(posts)
    key = "preset_collect_capped" if capped else "preset_collect_count"
    text = t(lang, key, n=n, max=PRESET_FWD_MAX)
    kb = preset_collect_kb(n, lang)
    prev = context.user_data.get("preset_fwd_msg")
    if prev:
        try:
            await context.bot.delete_message(chat_id, prev)
        except Exception:  # noqa: BLE001 — already gone / too old
            pass
    m = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)
    context.user_data["preset_fwd_msg"] = m.message_id


async def preset_fwd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data["plib_mode"] = "await_forward"
    context.user_data["preset_fwd_posts"] = []
    context.user_data.pop("preset_fwd_msg", None)
    await q.edit_message_text(
        t(lang, "preset_fwd_howto"), parse_mode=ParseMode.HTML,
        reply_markup=preset_collect_kb(0, lang),
    )
    return A_PROMPT


async def on_preset_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A forwarded post arrived at the prompt step → buffer it for preset generation."""
    msg = update.message
    lang = _lang(context)
    html_text = _post_html(msg).strip()
    if not html_text:
        await msg.reply_text(t(lang, "preset_fwd_no_text"), parse_mode=ParseMode.HTML)
        return A_PROMPT

    posts = context.user_data.setdefault("preset_fwd_posts", [])
    context.user_data["plib_mode"] = "await_forward"
    if len(posts) >= PRESET_FWD_MAX:
        await _show_collect_summary(context, msg.chat_id, lang, capped=True)
        return A_PROMPT
    posts.append(html_text)
    await _show_collect_summary(context, msg.chat_id, lang)
    return A_PROMPT


async def preset_collect_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """✖️ Cancel during collection → drop the buffer, back to the library."""
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    for k in ("plib_mode", "preset_fwd_posts", "preset_fwd_msg", "preset_mode_char"):
        context.user_data.pop(k, None)
    return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))


async def _render_mode_picker(q, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    """(Re)draw the character picker on `q`'s message."""
    char = context.user_data.get("preset_mode_char", "unified")
    n = len(context.user_data.get("preset_fwd_posts", []))
    await q.edit_message_text(
        t(lang, "preset_mode_title", n=n),
        parse_mode=ParseMode.HTML,
        reply_markup=preset_mode_kb(char, lang),
    )


async def preset_show_modes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """⚡️ Create → show the character picker instead of generating at once."""
    q = update.callback_query
    lang = _lang(context)
    posts = context.user_data.get("preset_fwd_posts", [])
    if not posts:
        await q.answer(t(lang, "preset_collect_empty"), show_alert=True)
        return A_PROMPT

    creds = await _resolve_creds_for_flow(context)
    if not creds or not creds.get("api_key"):
        await q.answer()
        await q.edit_message_text(
            t(lang, "preset_suggest_fail", error="нет ключа или модели у агента"),
            parse_mode=ParseMode.HTML,
        )
        return A_PROMPT

    await q.answer()
    context.user_data.setdefault("preset_mode_char", "unified")
    context.user_data.pop("preset_fwd_msg", None)
    await _render_mode_picker(q, context, lang)
    return A_PROMPT


async def preset_mode_set_char(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = _lang(context)
    val = q.data.split(":")[2]
    if val not in ("unified", "scenarios") or val == context.user_data.get("preset_mode_char", "unified"):
        await q.answer()
        return A_PROMPT
    context.user_data["preset_mode_char"] = val
    await q.answer()
    await _render_mode_picker(q, context, lang)
    return A_PROMPT


async def preset_collect_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """⚡️ Generate → send all buffered posts to the AI and propose a preset."""
    q = update.callback_query
    lang = _lang(context)
    posts = list(context.user_data.get("preset_fwd_posts", []))
    if not posts:
        await q.answer(t(lang, "preset_collect_empty"), show_alert=True)
        return A_PROMPT

    creds = await _resolve_creds_for_flow(context)
    if not creds or not creds.get("api_key"):
        await q.answer()
        await q.edit_message_text(
            t(lang, "preset_suggest_fail", error="нет ключа или модели у агента"),
            parse_mode=ParseMode.HTML,
        )
        return A_PROMPT

    char_mode = context.user_data.get("preset_mode_char", "unified")

    await q.answer()
    for k in ("plib_mode", "preset_fwd_msg"):
        context.user_data.pop(k, None)
    await q.edit_message_text(
        t(lang, "preset_analyzing_n", n=len(posts)), parse_mode=ParseMode.HTML,
    )

    prov = get_provider(creds["provider"])
    messages = _suggest_messages(posts, char_mode)
    try:
        result = await queue.enqueue(
            lambda: prov.chat(creds["api_base"], creds["api_key"], creds["model"], messages)
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Preset suggestion failed: %s", e)
        await q.edit_message_text(
            t(lang, "preset_suggest_fail", error=html.escape(str(e)[:300])),
            parse_mode=ParseMode.HTML,
        )
        return A_PROMPT

    result = (result or "").strip()
    if not result:
        await q.edit_message_text(
            t(lang, "preset_suggest_fail", error="пустой ответ модели"),
            parse_mode=ParseMode.HTML,
        )
        return A_PROMPT

    context.user_data["preset_suggested"] = result
    for k in ("preset_fwd_posts", "preset_mode_char"):
        context.user_data.pop(k, None)
    disp = html.escape(result)
    if len(disp) > 3500:
        disp = disp[:3500] + "…"
    await q.edit_message_text(
        t(lang, "preset_suggested_title", body=disp),
        parse_mode=ParseMode.HTML,
        reply_markup=preset_suggest_kb(lang),
    )
    return A_PROMPT


async def preset_suggest_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = _lang(context)
    await q.answer(t(lang, "prompt_preset_applied"))
    body = context.user_data.get("preset_suggested", "")
    return await _apply_body(update, context, body)


async def preset_suggest_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    if not context.user_data.get("preset_suggested"):
        # Stale button (suggestion already consumed) — fall back to the library.
        return await _render_library(q, context, lang, context.user_data.get("preset_page", 0))
    context.user_data["plib_mode"] = "save_name"
    await q.edit_message_text(t(lang, "preset_suggest_save_name"), parse_mode=ParseMode.HTML)
    return A_PROMPT


async def preset_suggest_discard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context)
    context.user_data.pop("preset_suggested", None)
    context.user_data.pop("plib_mode", None)
    return await _render_library(q, context, lang, 0)


# ───── Text router for preset sub-flows (name / body / save-name) ─────
async def _plib_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle a typed message that belongs to a preset sub-flow, selected by the
    `plib_mode` flag. Returns A_PROMPT (or a terminal state) when it handled the
    message, or None to let the normal prompt-save logic run.
    """
    mode = context.user_data.get("plib_mode")
    if mode not in ("new_name", "new_body", "save_name", "share_lookup"):
        return None
    lang = _lang(context)
    text = (update.message.text or "").strip()

    if mode == "share_lookup":
        name = context.user_data.get("preset_sel_name", "")
        if not text:
            await update.message.reply_text(
                t(lang, "preset_share_ask", name=html.escape(name)), parse_mode=ParseMode.HTML)
            return A_PROMPT
        target = await get_user_by_handle(text)
        if not target:
            await update.message.reply_text(t(lang, "preset_share_notfound"), parse_mode=ParseMode.HTML)
            return A_PROMPT
        if target["user_id"] == update.effective_user.id:
            await update.message.reply_text(t(lang, "preset_share_self"), parse_mode=ParseMode.HTML)
            return A_PROMPT
        if not target.get("accept_presets", 1):
            await update.message.reply_text(t(lang, "preset_share_blocked"), parse_mode=ParseMode.HTML)
            return A_PROMPT
        context.user_data["share_to"] = target["user_id"]
        context.user_data["share_to_lang"] = target.get("lang") or DEFAULT_LANG
        await update.message.reply_text(
            t(lang, "preset_share_confirm", name=html.escape(name), who=_who_label(target)),
            parse_mode=ParseMode.HTML, reply_markup=preset_share_confirm_kb(lang),
        )
        return A_PROMPT

    if mode == "new_name":
        if not text:
            await update.message.reply_text(t(lang, "preset_new_name"), parse_mode=ParseMode.HTML)
            return A_PROMPT
        context.user_data["plib_new_name"] = text[:64]
        context.user_data["plib_mode"] = "new_body"
        await update.message.reply_text(t(lang, "preset_new_body"), parse_mode=ParseMode.HTML)
        return A_PROMPT

    if mode == "new_body":
        if not text:
            await update.message.reply_text(t(lang, "preset_new_body"), parse_mode=ParseMode.HTML)
            return A_PROMPT
        name = context.user_data.pop("plib_new_name", "") or "Пресет"
        await create_user_preset(update.effective_user.id, name, text)
        context.user_data.pop("plib_mode", None)
        await update.message.reply_text(
            t(lang, "preset_created", name=html.escape(name)), parse_mode=ParseMode.HTML,
        )
        labels = await _build_preset_items(context, update.effective_user.id, lang)
        context.user_data["preset_page"] = 0
        await update.message.reply_text(
            t(lang, "preset_lib_title"), parse_mode=ParseMode.HTML,
            reply_markup=_library_kb(labels, 0, lang),
        )
        return A_PROMPT

    # mode == "save_name": name the AI-suggested preset, save it, then apply.
    if not text:
        await update.message.reply_text(t(lang, "preset_suggest_save_name"), parse_mode=ParseMode.HTML)
        return A_PROMPT
    body = context.user_data.get("preset_suggested", "")
    name = text[:64]
    await create_user_preset(update.effective_user.id, name, body)
    context.user_data.pop("plib_mode", None)
    await update.message.reply_text(
        t(lang, "preset_created", name=html.escape(name)), parse_mode=ParseMode.HTML,
    )
    return await _apply_body(update, context, body)


def _preset_state_handlers() -> list:
    """
    All preset-library handlers for the A_PROMPT state, shared by the create and
    edit-prompt conversations. The FORWARDED handler MUST precede the text
    handler the caller appends, so forwarded posts route to the AI suggester.
    Anchored patterns keep `^apreset:\\d+$` (view) from clashing with the
    `apreset:new/fwd/del/delyes/sapply/...` actions.
    """
    return [
        CallbackQueryHandler(open_preset_lib, pattern=r"^agent:plib$"),
        CallbackQueryHandler(preset_new_start, pattern=r"^apreset:new$"),
        CallbackQueryHandler(preset_fwd_start, pattern=r"^apreset:fwd$"),
        CallbackQueryHandler(preset_show_modes, pattern=r"^apreset:gen$"),
        CallbackQueryHandler(preset_mode_set_char, pattern=r"^apreset:mchar:(unified|scenarios)$"),
        CallbackQueryHandler(preset_collect_create, pattern=r"^apreset:gendo$"),
        CallbackQueryHandler(preset_collect_cancel, pattern=r"^apreset:fwdcancel$"),
        CallbackQueryHandler(preset_suggest_apply, pattern=r"^apreset:sapply$"),
        CallbackQueryHandler(preset_suggest_save, pattern=r"^apreset:ssave$"),
        CallbackQueryHandler(preset_suggest_discard, pattern=r"^apreset:sdiscard$"),
        CallbackQueryHandler(preset_apply, pattern=r"^apreset:apply$"),
        CallbackQueryHandler(preset_share_start, pattern=r"^apreset:share$"),
        CallbackQueryHandler(preset_share_send, pattern=r"^apreset:shsend$"),
        CallbackQueryHandler(preset_share_back, pattern=r"^apreset:shback$"),
        CallbackQueryHandler(preset_share_cancel, pattern=r"^apreset:shcancel$"),
        CallbackQueryHandler(preset_back, pattern=r"^apreset:back$"),
        CallbackQueryHandler(preset_exit, pattern=r"^apreset:exit$"),
        CallbackQueryHandler(preset_delete_yes, pattern=r"^apreset:delyes:\d+$"),
        CallbackQueryHandler(preset_delete, pattern=r"^apreset:del:\d+$"),
        CallbackQueryHandler(preset_page, pattern=r"^apresetpage:\d+$"),
        CallbackQueryHandler(preset_view, pattern=r"^apreset:\d+$"),
        MessageHandler(filters.FORWARDED & ~filters.COMMAND, on_preset_forward),
    ]


async def preset_stale_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global catch for preset-library buttons tapped OUTSIDE an active prompt
    conversation (e.g. after a bot restart wiped the in-memory state). Without
    this the callbacks match nothing and the button silently does nothing;
    here we answer with a clear toast and drop the dead keyboard.
    """
    q = update.callback_query
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    await q.answer(t(lang, "preset_session_stale"), show_alert=True)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 — message may be uneditable/old
        pass


async def ask_edit_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    context.user_data["edit_agent_id"] = aid
    context.user_data["agent_lang"] = lang
    await q.edit_message_text(t(lang, "provider_enter_key"), parse_mode=ParseMode.HTML)
    return A_API_KEY


async def edit_key_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    aid = context.user_data.get("edit_agent_id")
    key = (update.message.text or "").strip()
    agent = await get_agent(aid) if aid else None
    if not agent:
        context.user_data.clear()
        return ConversationHandler.END
    provider = agent.get("provider") or "favoriteapi"
    api_base = agent.get("api_base") or get_provider(provider).default_api_base()
    status = await update.message.reply_text(t(lang, "provider_verifying"))
    try:
        await verify(provider, api_base, key)
    except Exception as e:
        await status.edit_text(t(lang, "provider_key_fail", error=str(e)[:300]))
        return A_API_KEY
    await update_agent(aid, api_key=key)
    await status.edit_text(t(lang, "provider_key_ok"))
    context.user_data.clear()
    await _render_card(update, context, aid, edit=False)
    return ConversationHandler.END


# ───── Edit model (re-fetch + picker) ─────
async def ask_edit_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split(":")[3])
    user = await get_user(q.from_user.id)
    lang = (user or {}).get("lang") or DEFAULT_LANG
    agent = await get_agent(aid)
    if not agent:
        await show_agents(update, context)
        return ConversationHandler.END
    context.user_data["edit_agent_id"] = aid
    context.user_data["agent_lang"] = lang
    provider = agent.get("provider") or "favoriteapi"
    api_base = agent.get("api_base") or get_provider(provider).default_api_base()
    try:
        models = await fetch_models(provider, api_base, agent.get("api_key") or "")
    except Exception:
        models = []
    if not models:
        models = ["default"]
    context.user_data["agent_models"] = models
    context.user_data["agent_model_view"] = None
    await q.edit_message_text(
        t(lang, "provider_choose_model"),
        reply_markup=model_kb(
            models, page=0, lang=lang,
            sel_prefix="amodel", page_prefix="amodelpage",
            back_cb=f"agent:view:{aid}", search_cb="amodel:search",
        ),
    )
    return A_MODEL


async def edit_model_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    aid = context.user_data.get("edit_agent_id")
    idx = int(q.data.split(":")[1])
    models = _active_models(context)
    model = models[idx] if 0 <= idx < len(models) else ""
    if aid:
        await update_agent(aid, model_id=model)
    context.user_data["agent_model_view"] = None
    context.user_data.pop("agent_models", None)
    eid = aid
    context.user_data.clear()
    await _render_card(update, context, eid, edit=True)
    return ConversationHandler.END


def get_agent_handlers() -> list:
    # Creation wizard
    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(begin, pattern=r"^agent:new$")],
        states={
            A_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            A_PROVIDER: [CallbackQueryHandler(on_provider, pattern=r"^agent:setprov:")],
            A_API_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_api_base)],
            A_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_api_key)],
            A_MODEL: [
                CallbackQueryHandler(on_model_search, pattern=r"^amodel:search$"),
                CallbackQueryHandler(on_model, pattern=r"^amodel:\d+$"),
                CallbackQueryHandler(on_model_page, pattern=r"^amodelpage:\d+$"),
            ],
            A_MODEL_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_model_search_text)],
            A_PROMPT: _preset_state_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_prompt),
            ],
            A_SYS_TOGGLE: [
                CallbackQueryHandler(on_sys_toggle, pattern=r"^agent:sys$"),
                CallbackQueryHandler(on_sys_done, pattern=r"^agent:sysdone$"),
            ],
            A_BIND: [
                CallbackQueryHandler(on_bind_skip, pattern=r"^agent:bind_skip$"),
                MessageHandler(filters.FORWARDED & ~filters.COMMAND, on_bind_forward),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(skip_setup, pattern=r"^agent:skip_setup$"),
            CallbackQueryHandler(cancel_to_list, pattern=r"^agent:list$"),
            CallbackQueryHandler(cancel_to_home, pattern=r"^menu:home$"),
        ],
        allow_reentry=True,
        per_message=False,
        name="agent_create",
        persistent=False,
    )

    # Edit name
    edit_name_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_edit_name, pattern=r"^agent:edit:name:")],
        states={A_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name_text)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True, per_message=False, name="agent_edit_name", persistent=False,
    )

    # Edit prompt
    edit_prompt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_edit_prompt, pattern=r"^agent:edit:prompt:")],
        states={A_PROMPT: _preset_state_handlers() + [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_prompt_text),
        ]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_to_card, pattern=r"^agent:view:"),
        ],
        allow_reentry=True, per_message=False, name="agent_edit_prompt", persistent=False,
    )

    # Edit key
    edit_key_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_edit_key, pattern=r"^agent:edit:key:")],
        states={A_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_key_text)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True, per_message=False, name="agent_edit_key", persistent=False,
    )

    # Edit model
    edit_model_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_edit_model, pattern=r"^agent:edit:model:")],
        states={
            A_MODEL: [
                CallbackQueryHandler(on_model_search, pattern=r"^amodel:search$"),
                CallbackQueryHandler(edit_model_select, pattern=r"^amodel:\d+$"),
                CallbackQueryHandler(on_model_page, pattern=r"^amodelpage:\d+$"),
            ],
            A_MODEL_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_model_search_text)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_to_card, pattern=r"^agent:view:"),
            CallbackQueryHandler(cancel_to_home, pattern=r"^menu:home$"),
        ],
        allow_reentry=True, per_message=False, name="agent_edit_model", persistent=False,
    )

    # Bind a channel to an existing agent (from its channels submenu)
    addchan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(addchan_start, pattern=r"^agent:addchan:\d+$")],
        states={
            A_BIND: [
                CallbackQueryHandler(addchan_back, pattern=r"^agent:chans:"),
                MessageHandler(filters.FORWARDED & ~filters.COMMAND, addchan_forward),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(addchan_back, pattern=r"^agent:chans:"),
            CallbackQueryHandler(cancel_to_home, pattern=r"^menu:home$"),
        ],
        allow_reentry=True, per_message=False, name="agent_addchan", persistent=False,
    )

    return [
        create_conv,
        edit_name_conv,
        edit_prompt_conv,
        edit_key_conv,
        edit_model_conv,
        addchan_conv,
        CallbackQueryHandler(skip_setup, pattern=r"^agent:skip_setup$"),
        CallbackQueryHandler(show_agents, pattern=r"^agent:list$"),
        CallbackQueryHandler(show_agent_card, pattern=r"^agent:view:"),
        CallbackQueryHandler(on_edit_provider, pattern=r"^agent:edit:provider:"),
        CallbackQueryHandler(on_set_provider, pattern=r"^agent:setprov:[^:]+:\d+$"),
        CallbackQueryHandler(on_toggle_sys, pattern=r"^agent:edit:sys:"),
        CallbackQueryHandler(on_toggle_mode, pattern=r"^agent:mode:\d+$"),
        CallbackQueryHandler(on_toggle_fwd, pattern=r"^agent:fwd:\d+$"),
        CallbackQueryHandler(show_channels, pattern=r"^agent:chans:"),
        CallbackQueryHandler(on_del_channel, pattern=r"^agent:delchan:"),
        CallbackQueryHandler(on_delete_yes, pattern=r"^agent:del_yes:"),
        CallbackQueryHandler(on_delete, pattern=r"^agent:del:"),
        # Last resort: preset-library buttons whose conversation no longer exists
        # (bot restart / timeout). Must come AFTER the conversations so it only
        # fires when none of them claimed the callback.
        CallbackQueryHandler(preset_stale_cb, pattern=r"^(apreset:|apresetpage:|agent:plib$)"),
    ]
