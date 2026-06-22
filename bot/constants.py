"""
Shared constants: callback namespaces, conversation states, settings keys.
Keeping these in one place avoids string-typos between keyboards and routers.
"""

# --- Callback-data namespaces (prefix:action[:param...]) -------------------
CB_MENU = "menu"        # menu:home|settings|channels|stats|provider|prompt|help|admin
CB_SETTINGS = "s"       # s:toggle_sys|toggle_preview|lang|reset_ctx|reset_stats|...
CB_PROVIDER = "prov"    # prov:<name>|prov:test|prov:setkey|prov:setbase|prov:setmodel
CB_MODEL = "model"      # model:<model_id>
CB_CHANNEL = "chan"     # chan:view|add|toggle|remove|active:<channel_id>
CB_PREVIEW = "preview"  # preview:ok|no|edit:<channel_id>:<msg_id>
CB_PROMPT = "prompt"    # prompt:view|edit|presets|use|toggle_sys
CB_LANG = "lang"        # lang:ru|lang:en
CB_ADMIN = "admin"      # admin:users|stats|broadcast|logs|banner|desc|ban|unban|...
CB_SETUP = "setup"      # setup:* (onboarding inline steps)
CB_AGENT = "agent"      # agent:list|new|view|edit|setprov|chans|addchan|delchan|del:<id>
CB_NOOP = "noop"        # inert button (e.g. pagination label)

# --- Provider order (display) ----------------------------------------------
PROVIDER_ORDER = ["favoriteapi", "openrouter", "freemodel", "openmodel", "nvidia", "deepseek"]

# --- Settings (KV) keys ----------------------------------------------------
SET_BANNER_TYPE = "menu_banner_type"       # photo | video | none
SET_BANNER_FILE_ID = "menu_banner_file_id"
SET_BOT_DESCRIPTION = "bot_description"
SET_BOT_SHORT_DESCRIPTION = "bot_short_description"
SET_SUPPORT_ID = "support_id"               # numeric Telegram id of support contact
SET_MENU_CHANNEL_ENABLED = "menu_channel_enabled"   # "1" | "0"
SET_MENU_CHANNEL_LINK = "menu_channel_link"         # public/invite URL shown in the menu
SET_MENU_CHANNEL_ID = "menu_channel_id"             # resolved channel id (-100…)

BANNER_NONE = "none"
BANNER_PHOTO = "photo"
BANNER_VIDEO = "video"

# --- Pagination ------------------------------------------------------------
PAGE_SIZE_MODELS = 12
PAGE_SIZE_USERS = 8
PAGE_SIZE_LOGS = 15

# --- Conversation states ---------------------------------------------------
# Onboarding (setup.py)
(
    S_PROVIDER,
    S_API_BASE,
    S_API_KEY,
    S_MODEL,
    S_PROMPT,
    S_SYS_TOGGLE,
) = range(6)

# Agent creation wizard (agent.py)
(
    A_NAME,
    A_PROVIDER,
    A_API_BASE,
    A_API_KEY,
    A_MODEL,
    A_PROMPT,
    A_SYS_TOGGLE,
    A_BIND,
    A_MODEL_SEARCH,
) = range(9)

# Single-value text-input flows (settings/provider/prompt/channel/admin)
(
    T_EDIT_KEY,
    T_EDIT_BASE,
    T_EDIT_MODEL,
    T_EDIT_PROMPT,
    T_ADD_CHANNEL,
    T_BROADCAST,
    T_BANNER_MEDIA,
    T_DESC_LONG,
    T_DESC_SHORT,
    T_PREVIEW_EDIT,
    T_SUPPORT_ID,
    T_MENUCHAN_ID,
    T_MENUCHAN_LINK,
    T_USER_SEARCH,
) = range(100, 114)
