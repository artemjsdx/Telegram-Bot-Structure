from .favoriteapi import FavoriteAPIProvider
from .openrouter import OpenRouterProvider
from .freemodel import FreeModelProvider
from .openmodel import OpenModelProvider
from .nvidia import NvidiaProvider
from .base import BaseProvider

PROVIDERS: dict[str, BaseProvider] = {
    "favoriteapi": FavoriteAPIProvider(),
    "openrouter": OpenRouterProvider(),
    "freemodel": FreeModelProvider(),
    "openmodel": OpenModelProvider(),
    "nvidia": NvidiaProvider(),
}


def get_provider(name: str) -> BaseProvider:
    """Return provider by name, falling back to FavoriteAPI if unknown."""
    return PROVIDERS.get(name, PROVIDERS["favoriteapi"])


def list_providers() -> list[BaseProvider]:
    """Return all registered providers in display order."""
    return list(PROVIDERS.values())