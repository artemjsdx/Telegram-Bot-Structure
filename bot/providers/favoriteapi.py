import asyncio
import httpx
from .base import BaseProvider

TIMEOUT = 90.0

FALLBACK_MODELS = [
    "gemini-3.0-flash",
    "gemini-3.0-flash-thinking",
    "gemini-2.5-flash",
    "gemini-2.5-flash-thinking",
]

# Skips ngrok's browser-interstitial when the base is an ngrok tunnel; harmless otherwise.
_SKIP_NGROK = {"ngrok-skip-browser-warning": "true"}


class FavoriteAPIProvider(BaseProvider):
    name = "favoriteapi"
    display_name = "FavoriteAPI ⭐"

    def requires_api_base(self) -> bool:
        return True

    def default_api_base(self) -> str:
        return ""

    async def verify_key(self, api_base: str, api_key: str) -> dict:
        url = f"{api_base.rstrip('/')}/api/v1/me"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _extract_ids(data: dict) -> list[str]:
        models = (data or {}).get("models", [])
        ids = [
            (m.get("id") or m.get("name", "")) if isinstance(m, dict) else str(m)
            for m in models
        ]
        return [i for i in ids if i]

    async def get_models(self, api_base: str, api_key: str) -> list[str]:
        # The public /api/models returns the FULL catalog (all available models).
        # The key-scoped /api/v1/models only lists the key's allowed + recommended
        # set, so use it merely as a fallback when the public list is unavailable.
        base = api_base.rstrip("/")
        sources = (
            (f"{base}/api/models", dict(_SKIP_NGROK)),
            (f"{base}/api/v1/models", {**_SKIP_NGROK, "Authorization": f"Bearer {api_key}"}),
        )
        for url, headers in sources:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    r = await client.get(url, headers=headers)
                if r.status_code != 200:
                    continue
                ids = self._extract_ids(r.json())
                if ids:
                    return ids
            except Exception:
                continue
        return FALLBACK_MODELS

    async def chat(
        self,
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict],
        max_retries: int = 5,
    ) -> str:
        url = f"{api_base.rstrip('/')}/api/v1/chat"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {"messages": messages}
        if model:
            payload["model"] = model

        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(url, json=payload, headers=headers)
                data = r.json()
                log_code = data.get("log_code", "")
                if log_code == "KEY_BUSY_301":
                    wait = 10 * (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                choices = data.get("choices", [])
                if choices:
                    return choices[0]["message"]["content"]
                raise ValueError(f"No choices in response: {data}")

        raise RuntimeError("FavoriteAPI key busy after max retries")