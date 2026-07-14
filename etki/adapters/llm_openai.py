"""OpenAI-compatible LLM client (incl. vLLM). Phase 1 seam — used only when
`ETKI_LLM_BASE_URL` is configured; otherwise the heuristic extraction
path is used. Not run in CI without a live endpoint.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "qwen2.5-coder",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", headers=headers, json=body
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM beklenen JSON nesnesini döndürmedi")
        return parsed
