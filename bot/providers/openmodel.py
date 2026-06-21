"""
OpenModel provider — Anthropic Messages route (api.openmodel.ai).

OpenModel is a multi-protocol gateway ("OpenRouter alternative") that exposes
three upstream-compatible routes on the same base:
  • /v1/responses                         — OpenAI Responses (Bearer auth)
  • /v1/messages                          — Anthropic Messages (x-api-key + anthropic-version) — used here
  • /v1beta/models/<m>:generateContent    — Gemini

There is no /chat/completions route (it 404s "route not found"), so we talk to
the Anthropic Messages endpoint, which maps 1:1 onto our internal
messages=[{role, content}] format. Keys are prefixed `om-`. We send both
x-api-key and Authorization: Bearer so the key is accepted regardless of which
convention the gateway enforces for a given model.
"""
import httpx

from .base import BaseProvider

TIMEOUT = 120.0
ANTHROPIC_VERSION = "2023-06-01"

# Example model IDs from api.openmodel.ai docs; the live /v1/models list
# overrides these when reachable.
FALLBACK_MODELS = [
    "claude-sonnet-4-20250514",
    "deepseek-chat",
    "gpt-4o",
]


class OpenModelProvider(BaseProvider):
    name = "openmodel"
    display_name = "🌐 OpenModel"

    def requires_api_base(self) -> bool:
        return False

    def default_api_base(self) -> str:
        return "https://api.openmodel.ai/v1"

    def _headers(self, api_key: str) -> dict:
        return {
            "x-api-key": api_key,
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": ANTHROPIC_VERSION,
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

    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
        """Anthropic wants the system prompt at the top level, not in messages."""
        system_parts: list[str] = []
        convo: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                content = m.get("content")
                if isinstance(content, str) and content:
                    system_parts.append(content)
            else:
                convo.append(m)
        return "\n".join(system_parts), convo

    async def chat(
        self,
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict],
        max_retries: int = 5,
    ) -> str:
        base = (api_base or self.default_api_base()).rstrip("/")
        system, convo = self._split_system(messages)
        payload = {
            "model": model or FALLBACK_MODELS[0],
            "max_tokens": 4096,
            "messages": convo,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{base}/messages", json=payload, headers=self._headers(api_key)
            )
            try:
                data = r.json()
            except Exception:
                data = None

            # A non-2xx status or an `error` field both mean failure; surface the
            # server message verbatim so the owner sees the real cause (quota, etc).
            err = data.get("error") if isinstance(data, dict) else None
            if r.status_code >= 400 or err is not None:
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("type") or f"HTTP {r.status_code}"
                elif isinstance(err, str):
                    msg = err
                else:
                    msg = (data.get("message") if isinstance(data, dict) else None) or f"HTTP {r.status_code}"
                raise RuntimeError(f"🌐 OpenModel: {msg}")

            # Anthropic Messages response: content is a list of blocks; keep text.
            blocks = (data or {}).get("content", [])
            if isinstance(blocks, list):
                text = "".join(
                    b.get("text", "")
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text"
                )
                if text:
                    return text
            raise ValueError(f"🌐 OpenModel: пустой ответ ({data})")
