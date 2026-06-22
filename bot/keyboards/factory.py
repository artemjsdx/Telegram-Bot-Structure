"""
Inline-keyboard factory. Every builder takes `lang` and pulls labels from texts,
so callback_data stays language-independent while captions are localized.
Callback conventions live in constants.py.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from constants import (
    PROVIDER_ORDER,
    PAGE_SIZE_MODELS,
    PAGE_SIZE_USERS,
    BANNER_NONE,
    BANNER_PHOTO,
    BANNER_VIDEO,
)
from texts import t

PROVIDER_LABELS = {
    "favoriteapi": "FavoriteAPI ⭐",
    "openrouter": "OpenRouter 🔀",
    "freemodel": "FreeModel 🆓",
    "openmodel": "OpenModel 🌐",
    "nvidia": "NVIDIA 💚",
    "deepseek": "DeepSeek 🐳",
}


# ───── Generic buttons ─────
def back_btn(cb: str, lang: str = "ru") -> InlineKeyboardButton:
    return InlineKeyboardButton(t(lang, "btn_back"), callback_data=cb)


def home_btn(lang: str = "ru") -> InlineKeyboardButton:
    return InlineKeyboardButton(t(lang, "btn_home"), callback_data="menu:home")


# ───── Main menu ─────
def main_menu_kb(lang: str = "ru", is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(lang, "menu_provider"), callback_data="menu:provider"),
         InlineKeyboardButton(t(lang, "menu_prompt"), callback_data="menu:prompt")],
        [InlineKeyboardButton(t(lang, "menu_channels"), callback_data="menu:channels"),
         InlineKeyboardButton(t(lang, "menu_stats"), callback_data="menu:stats")],
        [InlineKeyboardButton(t(lang, "menu_settings"), callback_data="menu:settings"),
         InlineKeyboardButton(t(lang, "menu_help"), callback_data="menu:help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(t(lang, "menu_admin"), callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows)


# ───── Agents (main screen) ─────
def agents_list_kb(agents: list[dict], lang: str = "ru", is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for a in agents:
        name = a.get("name") or f"#{a['agent_id']}"
        rows.append([InlineKeyboardButton(f"🤖 {name}", callback_data=f"agent:view:{a['agent_id']}")])
    rows.append([InlineKeyboardButton(t(lang, "agent_create"), callback_data="agent:new")])
    # Two-per-row so no label gets squeezed into a third of the width (was
    # truncating "📊 Статистика"). Help pairs with Admin when present, else stands alone.
    rows.append([
        InlineKeyboardButton(t(lang, "menu_settings"), callback_data="menu:settings"),
        InlineKeyboardButton(t(lang, "menu_stats"), callback_data="menu:stats"),
    ])
    help_row = [InlineKeyboardButton(t(lang, "menu_help"), callback_data="menu:help")]
    if is_admin:
        help_row.append(InlineKeyboardButton(t(lang, "menu_admin"), callback_data="menu:admin"))
    rows.append(help_row)
    return InlineKeyboardMarkup(rows)


def agent_card_kb(agent_id: int, sys_on: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    aid = agent_id
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "agent_edit_name"), callback_data=f"agent:edit:name:{aid}"),
         InlineKeyboardButton(t(lang, "agent_edit_provider"), callback_data=f"agent:edit:provider:{aid}")],
        [InlineKeyboardButton(t(lang, "agent_edit_key"), callback_data=f"agent:edit:key:{aid}"),
         InlineKeyboardButton(t(lang, "agent_edit_model"), callback_data=f"agent:edit:model:{aid}")],
        [InlineKeyboardButton(t(lang, "agent_edit_prompt"), callback_data=f"agent:edit:prompt:{aid}"),
         InlineKeyboardButton(
             t(lang, "settings_sys_on") if sys_on else t(lang, "settings_sys_off"),
             callback_data=f"agent:edit:sys:{aid}")],
        [InlineKeyboardButton(t(lang, "agent_channels"), callback_data=f"agent:chans:{aid}")],
        [InlineKeyboardButton(t(lang, "agent_delete"), callback_data=f"agent:del:{aid}")],
        [back_btn("agent:list", lang), home_btn(lang)],
    ])


def agent_channels_kb(agent_id: int, channels: list[dict], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        title = ch.get("chan_title") or str(ch["channel_id"])
        rows.append([InlineKeyboardButton(
            f"⏹ 📣 {title}", callback_data=f"agent:delchan:{ch['channel_id']}:{agent_id}")])
    rows.append([InlineKeyboardButton(t(lang, "agent_add_channel"), callback_data=f"agent:addchan:{agent_id}")])
    rows.append([back_btn(f"agent:view:{agent_id}", lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


def agent_provider_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(PROVIDER_LABELS.get(p, p), callback_data=f"agent:setprov:{p}")]
            for p in PROVIDER_ORDER]
    return InlineKeyboardMarkup(rows)


# ───── Settings ─────
def settings_kb(user: dict, lang: str = "ru") -> InlineKeyboardMarkup:
    sys_on = bool(user.get("sys_prompt", 1))
    preview_on = bool(user.get("preview_mode", 0))
    shares_on = bool(user.get("accept_presets", 1))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            t(lang, "settings_sys_on") if sys_on else t(lang, "settings_sys_off"),
            callback_data="s:toggle_sys")],
        [InlineKeyboardButton(
            t(lang, "settings_preview_on") if preview_on else t(lang, "settings_preview_off"),
            callback_data="s:toggle_preview")],
        [InlineKeyboardButton(
            t(lang, "settings_shares_on") if shares_on else t(lang, "settings_shares_off"),
            callback_data="s:toggle_shares")],
        [InlineKeyboardButton(t(lang, "settings_lang", code=lang.upper()), callback_data="s:lang")],
        [InlineKeyboardButton(t(lang, "settings_reset_stats"), callback_data="s:reset_stats")],
        [home_btn(lang)],
    ])


def language_kb(current: str, lang: str = "ru") -> InlineKeyboardMarkup:
    def mark(code, label):
        return f"{label} ✅" if current == code else label
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mark("ru", "🇷🇺 Русский"), callback_data="lang:ru"),
         InlineKeyboardButton(mark("en", "🇬🇧 English"), callback_data="lang:en")],
        [back_btn("menu:settings", lang), home_btn(lang)],
    ])


# ───── Provider ─────
def provider_kb(current: str, configs: dict, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for pid in PROVIDER_ORDER:
        label = PROVIDER_LABELS.get(pid, pid)
        if current == pid:
            label += " ✅"
        elif configs.get(pid, {}).get("api_key"):
            label += " 🔑"
        rows.append([InlineKeyboardButton(label, callback_data=f"prov:set:{pid}")])
    rows.append([
        InlineKeyboardButton(t(lang, "provider_test"), callback_data="prov:test"),
        InlineKeyboardButton(t(lang, "provider_set_model"), callback_data="prov:setmodel"),
    ])
    rows.append([
        InlineKeyboardButton(t(lang, "provider_set_key"), callback_data="prov:setkey"),
        InlineKeyboardButton(t(lang, "provider_set_base"), callback_data="prov:setbase"),
    ])
    rows.append([home_btn(lang)])
    return InlineKeyboardMarkup(rows)


# ───── Model picker (index-based, paginated) ─────
def model_kb(
    models: list[str],
    page: int = 0,
    lang: str = "ru",
    sel_prefix: str = "model",
    page_prefix: str = "modelpage",
    back_cb: str = "menu:provider",
    search_cb: str | None = None,
    skip_cb: str | None = None,
) -> InlineKeyboardMarkup:
    """Buttons carry the model's index in `models` to stay within callback limits."""
    start = page * PAGE_SIZE_MODELS
    chunk = list(enumerate(models))[start:start + PAGE_SIZE_MODELS]
    rows = []
    for i in range(0, len(chunk), 2):
        row = [InlineKeyboardButton(chunk[i][1], callback_data=f"{sel_prefix}:{chunk[i][0]}")]
        if i + 1 < len(chunk):
            row.append(InlineKeyboardButton(chunk[i + 1][1], callback_data=f"{sel_prefix}:{chunk[i + 1][0]}"))
        rows.append(row)
    rows += _pager(page, len(models), PAGE_SIZE_MODELS, page_prefix)
    if search_cb:
        rows.append([InlineKeyboardButton(t(lang, "model_search"), callback_data=search_cb)])
    if skip_cb:
        rows.append([InlineKeyboardButton(t(lang, "agent_skip_setup"), callback_data=skip_cb)])
    rows.append([back_btn(back_cb, lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


# ───── Prompt ─────
def prompt_kb(user: dict, lang: str = "ru") -> InlineKeyboardMarkup:
    sys_on = bool(user.get("sys_prompt", 1))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "prompt_view"), callback_data="prompt:view"),
         InlineKeyboardButton(t(lang, "prompt_edit"), callback_data="prompt:edit")],
        [InlineKeyboardButton(t(lang, "prompt_presets"), callback_data="prompt:presets")],
        [InlineKeyboardButton(
            t(lang, "settings_sys_on") if sys_on else t(lang, "settings_sys_off"),
            callback_data="prompt:toggle_sys")],
        [home_btn(lang)],
    ])


def presets_kb(presets: list[str], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📄 {name}", callback_data=f"prompt:use:{i}")]
            for i, name in enumerate(presets)]
    rows.append([back_btn("menu:prompt", lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


# ───── Preset library (agent wizard / card; paginated) ─────
PAGE_SIZE_PRESETS = 8


def preset_lib_kb(
    labels: list[str],
    page: int = 0,
    lang: str = "ru",
    back_cb: str = "apreset:exit",
    sel_prefix: str = "apreset",
    page_prefix: str = "apresetpage",
    create_cb: str | None = None,
    fwd_cb: str | None = None,
) -> InlineKeyboardMarkup:
    """
    List of presets; buttons carry the preset's index to stay within callback
    limits. `labels` are already decorated with an emoji (⭐ for the user's own
    favorites, 📄 for the global read-only ones). Optional top row lets the user
    create their own preset or ask the AI to suggest one from a forwarded post.
    """
    rows: list[list[InlineKeyboardButton]] = []
    top = []
    if create_cb:
        top.append(InlineKeyboardButton(t(lang, "preset_new_btn"), callback_data=create_cb))
    if fwd_cb:
        top.append(InlineKeyboardButton(t(lang, "preset_fwd_btn"), callback_data=fwd_cb))
    if top:
        rows.append(top)

    start = page * PAGE_SIZE_PRESETS
    chunk = list(enumerate(labels))[start:start + PAGE_SIZE_PRESETS]
    rows += [[InlineKeyboardButton(lbl, callback_data=f"{sel_prefix}:{i}")] for i, lbl in chunk]
    rows += _pager(page, len(labels), PAGE_SIZE_PRESETS, page_prefix)
    rows.append([back_btn(back_cb, lang)])
    return InlineKeyboardMarkup(rows)


def preset_detail_kb(lang: str = "ru", apply_cb: str = "apreset:apply",
                     back_cb: str = "apreset:back",
                     delete_cb: str | None = None,
                     share_cb: str | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(lang, "preset_apply"), callback_data=apply_cb)]]
    if share_cb:
        rows.append([InlineKeyboardButton(t(lang, "preset_share_btn"), callback_data=share_cb)])
    if delete_cb:
        rows.append([InlineKeyboardButton(t(lang, "preset_delete_btn"), callback_data=delete_cb)])
    rows.append([InlineKeyboardButton(t(lang, "preset_back"), callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


def preset_share_confirm_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Sender's confirm screen: send / back to recipient lookup / cancel to home."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "preset_share_send_btn"), callback_data="apreset:shsend")],
        [InlineKeyboardButton(t(lang, "pshare_back_btn"), callback_data="apreset:shback")],
        [InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="apreset:shcancel")],
    ])


def pshare_offer_kb(share_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Recipient's offer keyboard: view / apply / save / reject."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "pshare_view_btn"), callback_data=f"pshare:view:{share_id}")],
        [InlineKeyboardButton(t(lang, "pshare_apply_btn"), callback_data=f"pshare:apply:{share_id}"),
         InlineKeyboardButton(t(lang, "pshare_save_btn"), callback_data=f"pshare:save:{share_id}")],
        [InlineKeyboardButton(t(lang, "pshare_reject_btn"), callback_data=f"pshare:reject:{share_id}")],
    ])


def pshare_view_kb(share_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Recipient's view screen: same actions + back to the offer."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "pshare_apply_btn"), callback_data=f"pshare:apply:{share_id}"),
         InlineKeyboardButton(t(lang, "pshare_save_btn"), callback_data=f"pshare:save:{share_id}")],
        [InlineKeyboardButton(t(lang, "pshare_reject_btn"), callback_data=f"pshare:reject:{share_id}")],
        [InlineKeyboardButton(t(lang, "pshare_back_btn"), callback_data=f"pshare:offer:{share_id}")],
    ])


def pshare_pick_agent_kb(agents: list[dict], share_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Recipient picks which agent to apply the shared preset to."""
    rows = [[InlineKeyboardButton(
        f"🤖 {a.get('name') or a['agent_id']}",
        callback_data=f"pshare:applyto:{share_id}:{a['agent_id']}")]
        for a in agents]
    rows.append([InlineKeyboardButton(t(lang, "pshare_back_btn"), callback_data=f"pshare:offer:{share_id}")])
    return InlineKeyboardMarkup(rows)


def preset_suggest_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Controls under an AI-suggested preset: apply / save+apply / discard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "preset_suggest_apply_btn"), callback_data="apreset:sapply")],
        [InlineKeyboardButton(t(lang, "preset_suggest_save_btn"), callback_data="apreset:ssave")],
        [InlineKeyboardButton(t(lang, "preset_suggest_discard_btn"), callback_data="apreset:sdiscard")],
    ])


def preset_collect_kb(n: int = 0, lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Shown while collecting forwarded posts for an AI preset. The 'generate'
    button appears only once at least one post is in the buffer; cancel always
    returns to the library.
    """
    rows = []
    if n > 0:
        rows.append([InlineKeyboardButton(t(lang, "preset_collect_gen_btn"), callback_data="apreset:gen")])
    rows.append([InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="apreset:fwdcancel")])
    return InlineKeyboardMarkup(rows)


def preset_mode_kb(char: str = "unified", lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Single-toggle picker before AI generation:
      • Character: 🎭 unified / 🎬 scenarios
    The active option is marked with ✅. Generation is always from scratch — there
    is no flow to feed the agent's current prompt back in, so no "base" toggle.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("✅ " if char == "unified" else "") + t(lang, "preset_mode_char_unified"),
            callback_data="apreset:mchar:unified"),
         InlineKeyboardButton(
            ("✅ " if char == "scenarios" else "") + t(lang, "preset_mode_char_scenarios"),
            callback_data="apreset:mchar:scenarios")],
        [InlineKeyboardButton(t(lang, "preset_mode_gen_btn"), callback_data="apreset:gendo")],
        [InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="apreset:fwdcancel")],
    ])


# ───── Channels ─────
def channels_kb(channels: list[dict], active_id: int | None, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        if not ch.get("active", 1):
            continue
        title = ch.get("chan_title") or str(ch["channel_id"])
        star = "⭐ " if ch["channel_id"] == active_id else ""
        rows.append([InlineKeyboardButton(
            f"{star}📣 {title}", callback_data=f"chan:view:{ch['channel_id']}")])
    rows.append([InlineKeyboardButton(t(lang, "channel_add"), callback_data="chan:add")])
    rows.append([home_btn(lang)])
    return InlineKeyboardMarkup(rows)


def channel_actions_kb(channel_id: int, is_active_default: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    if not is_active_default:
        rows.append([InlineKeyboardButton(t(lang, "channel_set_active"), callback_data=f"chan:active:{channel_id}")])
    rows.append([InlineKeyboardButton(t(lang, "channel_remove"), callback_data=f"chan:remove:{channel_id}")])
    rows.append([back_btn("menu:channels", lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


# ───── Confirm ─────
def confirm_kb(yes_cb: str, no_cb: str, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_yes"), callback_data=yes_cb),
        InlineKeyboardButton(t(lang, "btn_no"), callback_data=no_cb),
    ]])


# ───── Preview (approve/edit/reject) ─────
def preview_kb(channel_id: int, msg_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "preview_publish"), callback_data=f"preview:ok:{channel_id}:{msg_id}"),
         InlineKeyboardButton(t(lang, "preview_reject"), callback_data=f"preview:no:{channel_id}:{msg_id}")],
        [InlineKeyboardButton(t(lang, "preview_edit"), callback_data=f"preview:edit:{channel_id}:{msg_id}")],
    ])


def preview_edit_kb(channel_id: int, msg_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Single 'cancel' button shown while waiting for the user's corrected text."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_cancel"),
                              callback_data=f"preview:edit_cancel:{channel_id}:{msg_id}")],
    ])


# ───── Admin ─────
def admin_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "admin_users"), callback_data="admin:users:0"),
         InlineKeyboardButton(t(lang, "admin_stats"), callback_data="admin:stats")],
        [InlineKeyboardButton(t(lang, "admin_broadcast"), callback_data="admin:broadcast"),
         InlineKeyboardButton(t(lang, "admin_logs"), callback_data="admin:logs")],
        [InlineKeyboardButton(t(lang, "admin_banner"), callback_data="admin:banner"),
         InlineKeyboardButton(t(lang, "admin_desc"), callback_data="admin:desc")],
        [InlineKeyboardButton(t(lang, "admin_support"), callback_data="admin:support"),
         InlineKeyboardButton(t(lang, "admin_menuchan"), callback_data="admin:menuchan")],
        [home_btn(lang)],
    ])


def _user_label(u: dict) -> str:
    """
    Button label for a user: @username → first_name → id.
    Prefix = reachability flag; suffix = bound-channels marker
    (📎 exactly one, 🖇️ more than one).
    """
    uname = u.get("username")
    label = ("@" + uname) if uname else (u.get("first_name") or str(u["user_id"]))
    if len(label) > 24:
        label = label[:23] + "…"
    if u.get("is_banned"):
        flag = "🚫 "
    elif u.get("blocked"):
        flag = "👻 " if u.get("block_kind") == "deleted" else "⛔ "
    else:
        flag = ""
    n = u.get("chan_count")
    if n is None:
        n = len(u.get("channel_ids") or [])
    clip = " 🖇️" if n > 1 else (" 📎" if n == 1 else "")
    return f"{flag}{label}{clip}"


def admin_users_kb(
    users: list[dict],
    page: int,
    total: int,
    lang: str = "ru",
    page_prefix: str = "admin:users",
    show_search: bool = True,
    back_cb: str = "menu:admin",
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(_user_label(u), callback_data=f"admin:user:{u['user_id']}")]
            for u in users]
    rows += _pager(page, total, PAGE_SIZE_USERS, page_prefix)
    if show_search:
        rows.append([InlineKeyboardButton(t(lang, "admin_user_search"), callback_data="admin:usearch")])
    rows.append([back_btn(back_cb, lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


def _period_row(prefix: str, win: int, lang: str) -> list[InlineKeyboardButton]:
    """1д/7д/30д toggle row; the active window is marked with •."""
    def b(days: int, key: str) -> InlineKeyboardButton:
        label = t(lang, key)
        if win == days:
            label = "• " + label
        return InlineKeyboardButton(label, callback_data=f"{prefix}:{days}")
    return [b(1, "period_1d"), b(7, "period_7d"), b(30, "period_30d")]


def admin_user_card_kb(uid: int, banned: bool, win: int = 7, lang: str = "ru") -> InlineKeyboardMarkup:
    toggle = (InlineKeyboardButton(t(lang, "admin_user_unban"), callback_data=f"admin:unban:{uid}")
              if banned else
              InlineKeyboardButton(t(lang, "admin_user_ban"), callback_data=f"admin:ban:{uid}"))
    return InlineKeyboardMarkup([
        _period_row(f"admin:user:{uid}", win, lang),
        [toggle],
        [back_btn("admin:users:0", lang), home_btn(lang)],
    ])


def admin_stats_kb(win: int = 7, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("admin:stats", win, lang),
        [back_btn("menu:admin", lang), home_btn(lang)],
    ])


def stats_period_kb(win: int = 7, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("s:stats", win, lang),
        [home_btn(lang)],
    ])


def admin_support_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "admin_support_set"), callback_data="admin:support:set")],
        [back_btn("menu:admin", lang), home_btn(lang)],
    ])


def admin_menuchan_kb(enabled: bool, configured: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(lang, "admin_menuchan_setup"), callback_data="admin:menuchan:setup")]]
    if configured:
        toggle_key = "admin_menuchan_toggle_off" if enabled else "admin_menuchan_toggle_on"
        rows.append([InlineKeyboardButton(t(lang, toggle_key), callback_data="admin:menuchan:toggle")])
        rows.append([InlineKeyboardButton(t(lang, "admin_menuchan_clear"), callback_data="admin:menuchan:clear")])
    rows.append([back_btn("menu:admin", lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


def admin_banner_kb(current: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(lang, "admin_banner_photo"), callback_data="admin:banner:photo"),
         InlineKeyboardButton(t(lang, "admin_banner_video"), callback_data="admin:banner:video")],
    ]
    if current != BANNER_NONE:
        rows.append([InlineKeyboardButton(t(lang, "admin_banner_remove"), callback_data="admin:banner:remove")])
    rows.append([back_btn("menu:admin", lang), home_btn(lang)])
    return InlineKeyboardMarkup(rows)


def admin_desc_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "admin_desc_edit_long"), callback_data="admin:desc:long")],
        [InlineKeyboardButton(t(lang, "admin_desc_edit_short"), callback_data="admin:desc:short")],
        [back_btn("menu:admin", lang), home_btn(lang)],
    ])


# ───── Pagination helper ─────
def _pager(page: int, total: int, size: int, prefix: str) -> list[list[InlineKeyboardButton]]:
    pages = max(1, (total + size - 1) // size)
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}:{page + 1}"))
    return [row]
