"""
DeepSeek provider — OpenAI-compatible route (api.deepseek.com).

DeepSeek speaks the OpenAI protocol: Bearer auth with `sk-` keys, GET /models
for the catalogue, POST /chat/completions for chat. Its models are reasoning
models that also return a `reasoning_content` field — we only keep the final
`content`, which is the rewritten post.
"""
import httpx

from .base import BaseProvider

TIMEOUT = 120.0

# Used only if the live /v1/models list is unreachable.
FALLBACK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]


class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    display_name = "DeepSeek 🐋"

    def requires_api_base(self) -> bool:
        return False

    def default_api_base(self) -> str:
        return "https://api.deepseek.com/v1"

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def verify_key(self, api_base: str, api_key: str) -> dict:
        base = (api_base or self.default_api_base()).rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{base}/models", headers=self._headers(api_key))
            r.raise_for_status()
            return {"status": "ok"}

    async def get_models(self, api_base: str, api_key: str) -> list[str]:
        base = (api_base or self.default_api_base()).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{base}/models", headers=self._headers(api_key))
                if r.status_code != 200:
                    return FALLBACK_MODELS
                ids = [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
                return ids or FALLBACK_MODELS
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
        base = (api_base or self.default_api_base()).rstrip("/")
        payload = {
            "model": model or FALLBACK_MODELS[0],
            "messages": messages,
            "max_tokens": 4096,
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{base}/chat/completions", json=payload, headers=self._headers(api_key)
            )
            try:
                data = r.json()
            except Exception:
                data = None

            err = data.get("error") if isinstance(data, dict) else None
            if r.status_code >= 400 or err is not None:
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("error") or f"HTTP {r.status_code}"
                elif isinstance(err, str):
                    msg = err
                else:
                    msg = (data.get("message") if isinstance(data, dict) else None) or f"HTTP {r.status_code}"
                raise RuntimeError(f"DeepSeek 🐋: {msg}")

            choices = (data or {}).get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content")
                if content:
                    return content
            raise ValueError(f"DeepSeek 🐋: пустой ответ ({data})")
