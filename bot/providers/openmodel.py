"""
OpenModel provider — multi-protocol gateway (api.openmodel.ai).

OpenModel ("OpenRouter alternative") proxies several upstreams, each behind the
endpoint that matches its native protocol. There is NO /chat/completions route,
so we pick the route per model:
  • gpt-*            → POST /v1/responses                 (OpenAI Responses, Bearer)
  • gemini-*         → POST /v1beta/models/<m>:generateContent?key=…  (Gemini)
  • everything else  → POST /v1/messages                  (Anthropic Messages)
    (claude-*, deepseek-*, kimi-*, MiniMax-*, mimo-*)

All routes are reduced to plain text. Keys are prefixed `om-`. We send both
x-api-key and Authorization: Bearer so the key is accepted whichever convention
the chosen upstream enforces.
"""
import httpx

from .base import BaseProvider

TIMEOUT = 120.0
ANTHROPIC_VERSION = "2023-06-01"

# Sensible defaults (one per route) used only if the live /v1/models list is
# unreachable; normally get_models supplies the real catalogue.
FALLBACK_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.5",
    "deepseek-v4-pro",
    "gemini-3.5-flash",
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
                ids = [
                    m.get("id", "")
                    for m in r.json().get("data", [])
                    # Image-generation models can't produce the text a rewrite needs.
                    if m.get("id") and "image" not in m["id"].lower()
                ]
                return ids or FALLBACK_MODELS
        except Exception:
            return FALLBACK_MODELS

    @staticmethod
    def _route(model: str) -> str:
        m = (model or "").lower()
        if "gemini" in m:
            return "gemini"
        if m.startswith("gpt") or m.startswith(("o1", "o3", "o4")) or "codex" in m:
            return "responses"
        return "messages"

    @staticmethod
    def _err_message(data, status: int) -> str:
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return err.get("message") or err.get("type") or f"HTTP {status}"
        if isinstance(err, str):
            return err
        if isinstance(data, dict) and data.get("message"):
            return data["message"]
        return f"HTTP {status}"

    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        convo: list[dict] = []
        for m in messages:
            content = m.get("content")
            if m.get("role") == "system":
                if isinstance(content, str) and content:
                    system_parts.append(content)
            else:
                convo.append({"role": m.get("role", "user"), "content": content})
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
        model = model or FALLBACK_MODELS[0]
        route = self._route(model)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            if route == "responses":
                return await self._chat_responses(client, base, api_key, model, messages)
            if route == "gemini":
                return await self._chat_gemini(client, base, api_key, model, messages)
            return await self._chat_messages(client, base, api_key, model, messages)

    # ── Anthropic Messages (claude / deepseek / kimi / minimax / mimo) ──
    async def _chat_messages(self, client, base, api_key, model, messages) -> str:
        system, convo = self._split_system(messages)
        payload = {"model": model, "max_tokens": 4096, "messages": convo}
        if system:
            payload["system"] = system
        r = await client.post(f"{base}/messages", json=payload, headers=self._headers(api_key))
        data = self._json(r)
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            raise RuntimeError(f"🌐 OpenModel: {self._err_message(data, r.status_code)}")
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

    # ── OpenAI Responses (gpt-*) ──
    async def _chat_responses(self, client, base, api_key, model, messages) -> str:
        system, convo = self._split_system(messages)
        payload = {"model": model, "input": convo}
        if system:
            payload["instructions"] = system
        r = await client.post(f"{base}/responses", json=payload, headers=self._headers(api_key))
        data = self._json(r)
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            raise RuntimeError(f"🌐 OpenModel: {self._err_message(data, r.status_code)}")
        # Convenience field on some responses, else dig into the output items.
        text = data.get("output_text") if isinstance(data, dict) else None
        if not text:
            parts = []
            for item in (data or {}).get("output", []):
                if isinstance(item, dict) and item.get("type") == "message":
                    for c in item.get("content", []):
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            parts.append(c.get("text", ""))
            text = "".join(parts)
        if text:
            return text
        raise ValueError(f"🌐 OpenModel: пустой ответ ({data})")

    # ── Gemini (gemini-*) ──
    async def _chat_gemini(self, client, base, api_key, model, messages) -> str:
        host = base.rsplit("/v1", 1)[0]  # gateway root without the /v1 suffix
        system, convo = self._split_system(messages)
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m.get("content") or ""}],
            }
            for m in convo
        ]
        payload = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{host}/v1beta/models/{model}:generateContent?key={api_key}"
        r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        data = self._json(r)
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            raise RuntimeError(f"🌐 OpenModel: {self._err_message(data, r.status_code)}")
        cands = (data or {}).get("candidates", [])
        if cands:
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and not p.get("thought")
            )
            if text:
                return text
        raise ValueError(f"🌐 OpenModel: пустой ответ ({data})")

    @staticmethod
    def _json(r):
        try:
            return r.json()
        except Exception:
            return None
