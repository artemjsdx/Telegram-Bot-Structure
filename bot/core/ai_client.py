import asyncio
import httpx
from typing import Optional

TIMEOUT = 90.0


async def verify_key(api_base: str, api_key: str) -> dict:
    url = f"{api_base.rstrip('/')}/api/v1/me"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        r.raise_for_status()
        return r.json()


async def get_models(api_base: str, api_key: str) -> list[str]:
    url = f"{api_base.rstrip('/')}/api/v1/models"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        r.raise_for_status()
        data = r.json()
        models = data.get("models", [])
        if models and isinstance(models[0], dict):
            return [m.get("id") or m.get("name", "") for m in models]
        return [str(m) for m in models]


async def chat(
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
