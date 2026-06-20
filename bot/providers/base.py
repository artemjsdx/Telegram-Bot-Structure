from abc import ABC, abstractmethod


class BaseProvider(ABC):
    name: str
    display_name: str

    @abstractmethod
    async def verify_key(self, api_base: str, api_key: str) -> dict: ...

    @abstractmethod
    async def get_models(self, api_base: str, api_key: str) -> list[str]: ...

    @abstractmethod
    async def chat(
        self,
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict],
        max_retries: int = 5,
    ) -> str: ...

    def requires_api_base(self) -> bool:
        """Return True if this provider needs a user-supplied API base URL."""
        return True

    def default_api_base(self) -> str:
        """Default API base URL (empty = none)."""
        return ""