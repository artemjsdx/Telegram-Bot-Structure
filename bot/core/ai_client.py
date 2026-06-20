"""
Thin AI router: resolves a user's active provider + stored credentials
(provider_configs, with a fallback to the legacy users.* columns) and
delegates to the concrete provider implementation in bot/providers/.
"""
from __future__ import annotations

from db.storage import get_provider_config
from providers import get_provider


async def resolve_creds(user: dict) -> dict:
    """
    Resolve the active provider and its credentials for a user.
    Returns {provider, api_base, api_key, model}.
    """
    provider = user.get("provider") or "favoriteapi"
    cfg = await get_provider_config(user["user_id"], provider)
    if cfg:
        base = cfg.get("api_base") or ""
        key = cfg.get("api_key") or ""
        model = cfg.get("model_id") or ""
    else:
        base = user.get("api_base") or ""
        key = user.get("api_key") or ""
        model = user.get("model_id") or ""

    p = get_provider(provider)
    if not base:
        base = p.default_api_base()
    return {"provider": provider, "api_base": base, "api_key": key, "model": model}


async def chat_for_user(user: dict, messages: list[dict]) -> str:
    """Run a chat completion using the user's active provider + creds."""
    c = await resolve_creds(user)
    p = get_provider(c["provider"])
    return await p.chat(c["api_base"], c["api_key"], c["model"], messages)


def resolve_creds_from_agent(agent: dict) -> dict:
    """
    Resolve an agent's own provider + credentials.
    Returns {provider, api_base, api_key, model}. Empty api_base falls back to
    the provider's default base.
    """
    provider = agent.get("provider") or "favoriteapi"
    base = agent.get("api_base") or ""
    key = agent.get("api_key") or ""
    model = agent.get("model_id") or ""
    if not base:
        base = get_provider(provider).default_api_base()
    return {"provider": provider, "api_base": base, "api_key": key, "model": model}


async def verify(provider_name: str, api_base: str, api_key: str) -> dict:
    """Verify a key against a provider (used during setup / test connection)."""
    return await get_provider(provider_name).verify_key(api_base, api_key)


async def fetch_models(provider_name: str, api_base: str, api_key: str) -> list[str]:
    """List models for a provider."""
    return await get_provider(provider_name).get_models(api_base, api_key)
