import httpx
from .base import BaseProvider

TIMEOUT = 60.0

FALLBACK_MODELS = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3-haiku",
    "google/gemini-flash-1.5",
    "meta-llama/llama-3.1-8b-instruct:free",
]

# Curated popular models shown first when building model list
_POPULAR_MODELS = [
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o1-mini",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3-haiku",
    "google/gemini-pro-1.5",
    "google/gemini-flash-1.5",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mixtral-8x7b-instruct",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1:free",
    "qwen/qwen-2.5-72b-instruct",
    "microsoft/phi-3-medium-128k-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b",
    "cohere/command-r-plus",
]


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    display_name = "🔀 OpenRouter"

    def requires_api_base(self) -> bool:
        return False

    def default_api_base(self) -> str:
        return "https://openrouter.ai/api/v1"

    async def verify_key(self, api_base: str, api_key: str) -> dict:
        url = "https://openrouter.ai/api/v1/auth/key"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return r.json()

    async def get_models(self, api_base: str, api_key: str) -> list[str]:
        url = "https://openrouter.ai/api/v1/models"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if r.status_code != 200:
                    return FALLBACK_MODELS
                data = r.json()
                all_ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                # popular first, then the full remaining catalogue
                popular = [m for m in _POPULAR_MODELS if m in all_ids]
                others = [m for m in all_ids if m not in set(_POPULAR_MODELS)]
                combined = popular + others
                return combined if combined else FALLBACK_MODELS
        except Exception:
            return FALLBACK_MODELS

    async def chat(
        self,
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict],
        max_retries: int = 5,
    ) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/FavoriteStructure",
            "X-Title": "FavoriteStructure Bot",
        }
        payload = {
            "model": model or FALLBACK_MODELS[0],
            "messages": messages,
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0]["message"]["content"]
            raise ValueError(f"No choices in response: {data}")