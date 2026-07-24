"""Anthropic Claude API LLM client — implements the `LLMClient` port with the
official `anthropic` SDK. Activates only when `ETKI_LLM_PROVIDER=anthropic`
plus an API key (ANTHROPIC_API_KEY or ETKI_ANTHROPIC_API_KEY) is provided;
otherwise the heuristic extraction path is used. Not run in CI without a live key.

The core stays vendor-agnostic: engine/api only see the `LLMClient` port, never
this file (registry.build_llm_client selects it).
"""

from __future__ import annotations

import json
from typing import Any

# Default model — Claude Opus 4.8 (Anthropic's most capable Opus model).
DEFAULT_MODEL = "claude-opus-4-8"


def _strip_json_fences(text: str) -> str:
    """The LLM sometimes wraps JSON in a ```json ... ``` fence; strip the fence."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[: -3]
    return stripped.strip()


class AnthropicLLMClient:
    """Implements the `complete_json` port via the Claude Messages API
    (schema-constrained extraction)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        from anthropic import AsyncAnthropic  # lazy import: the SDK is an optional dependency

        # If api_key is None, the SDK resolves it from the ANTHROPIC_API_KEY environment.
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self._max_tokens = max_tokens

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        from anthropic.types import TextBlockParam

        system_text = (
            system + "\n\nRESPONSE: return exactly one valid JSON object; "
            "no explanation, preamble or code fence."
        )
        # Prompt caching: the system prefix (project preamble + injection guard +
        # this fixed RESPONSE instruction) is STABLE across calls, while `user`
        # varies. One AnthropicLLMClient is reused across every triage/extraction,
        # so a burst of calls (batch scope extraction, a triage flurry) reads the
        # system prefix from cache (~0.1x) instead of re-billing it. Byte-neutral:
        # cache_control changes only billing/latency, never the model's output.
        # A prefix below the model's cacheable minimum silently doesn't cache — no
        # error, no regression. Opus 4.8: temperature/top_p removed (400 if sent).
        system_blocks: list[TextBlockParam] = [
            {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
        ]
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        parsed = json.loads(_strip_json_fences(text))
        if not isinstance(parsed, dict):
            raise ValueError("LLM beklenen JSON nesnesini döndürmedi")
        return parsed
