"""LLM agent — lets an LLM use the index tools (IndexTools) via function calling.

Live demo of "the LLM talks to the index through MCP/tools". Two providers:
  - Anthropic Claude API: ETKI_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY
  - OpenAI-compatible (Ollama/vLLM): ETKI_LLM_BASE_URL=http://localhost:11434/v1
The tools are the same as the MCP server's.

Run: ETKI_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... \\
     uv run python -m etki.agent "bütçeyi aşar mı?"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx

from etki.config import Settings
from etki.index_tools import IndexTools, load_index_tools

_TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "scope_lookup",
            "description": "Talebe en yakın sözleşme kapsam maddelerini (dahil/hariç) getirir.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "impact_analysis",
            "description": "Bir modül ipucunun etkilenen kod bölgelerini getirir.",
            "parameters": {
                "type": "object",
                "properties": {"module": {"type": "string"}},
                "required": ["module"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "similar_effort",
            "description": "Benzer geçmiş işleri ve aralık efor tahminini getirir.",
            "parameters": {
                "type": "object",
                "properties": {"description": {"type": "string"}},
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "baseline_summary",
            "description": "Sözleşme baseline'ı ve kod grafiği özetini getirir.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dependency_impact",
            "description": (
                "Bir kütüphanenin (paket) ekleme/sürüm geçişi etki yüzeyini getirir: "
                "manifest bildirimi, kullanan modüller, etki yayılımı, churn ve LOC."
            ),
            "parameters": {
                "type": "object",
                "properties": {"package": {"type": "string"}},
                "required": ["package"],
            },
        },
    },
]

_SYSTEM = (
    "You are Etki's PMO decision-support assistant. Use the provided tools to "
    "answer the user's scope/impact/effort question. Answer briefly and with "
    "justification."
)


def _build_system(system_extra: str, lang: str) -> str:
    """Full system prompt: project preamble (domain/instructions) + agent role + language
    + injection guard."""
    from etki.llm_profile import UNTRUSTED_GUARD, language_directive

    head = f"{system_extra}\n\n" if system_extra else ""
    # Tool results (index/document content) and context embedded in the question may be
    # untrusted; the guard is ALWAYS appended, independently of system_extra.
    return f"{head}{_SYSTEM}\n\n{UNTRUSTED_GUARD}\n\n{language_directive(lang)}"


async def _translate(text: str, to_lang: str, settings: Settings) -> str:
    """Translates text into the target language (pivot step). Provider-agnostic
    (complete_json). On error → returns the original."""
    from etki.adapters.registry import build_llm_client

    client = build_llm_client(settings)
    if client is None or not text.strip():
        return text
    try:
        out = await client.complete_json(
            system=(
                f"You are a translator. Translate the user's text into '{to_lang}', preserving "
                'meaning and any markdown. Return only JSON: {"text": "<translation>"}.'
            ),
            user=text,
        )
        result = out.get("text")
        return result if isinstance(result, str) and result.strip() else text
    except Exception:  # noqa: BLE001
        return text


# Anthropic tool-use schema (derived from the OpenAI function schema — single source).
_ANTHROPIC_TOOLS: list[Any] = [
    {
        "name": t["function"]["name"],
        "description": t["function"]["description"],
        "input_schema": t["function"]["parameters"],
    }
    for t in _TOOL_SCHEMA
]


def _dispatch(tools: IndexTools, name: str, args: dict[str, Any]) -> Any:
    method = getattr(tools, name, None)
    if method is None:
        return {"error": f"bilinmeyen araç: {name}"}
    return method(**args)


async def _ask_anthropic(question: str, tools: IndexTools, settings: Settings, system: str) -> str:
    """Manual tool-call loop over the Claude Messages API (official anthropic SDK)."""
    from anthropic import AsyncAnthropic
    from anthropic.types import TextBlockParam

    client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=180.0)
    messages: list[Any] = [{"role": "user", "content": question}]
    # Cache the fixed prefix (tools render before system, so a breakpoint on the
    # single system block caches BOTH the tool schemas and the system prompt).
    # This prefix is re-sent on every one of the up-to-6 tool-loop iterations for
    # one question; caching it makes later iterations read it at ~0.1x instead of
    # re-billing the whole schema+preamble each turn. Byte-neutral.
    system_blocks: list[TextBlockParam] = [
        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
    ]
    for _ in range(6):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=system_blocks,
            tools=_ANTHROPIC_TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text")
            return text or "(boş yanıt)"
        messages.append({"role": "assistant", "content": response.content})
        results: list[Any] = []
        for block in response.content:
            if block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                result = _dispatch(tools, block.name, args)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        messages.append({"role": "user", "content": results})
    return "Yanıt üretilemedi (araç çağrısı döngüsü limiti aşıldı)."


async def ask(
    question: str,
    tools: IndexTools | None = None,
    *,
    system_extra: str = "",
    lang: str = "tr",
    pivot_language: str | None = None,
) -> str:
    settings = Settings()
    system = _build_system(system_extra, lang)
    # Optional pivot: translate input to the pivot language → reason → translate the
    # output back to the project language.
    use_pivot = bool(pivot_language) and pivot_language != lang
    asked = question
    if use_pivot:
        asked = await _translate(question, pivot_language, settings)  # type: ignore[arg-type]
    if (settings.llm_provider or "openai").lower() == "anthropic":
        if not (settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
            return (
                "Claude API anahtarı yok. Canlı ajan için: "
                "ETKI_LLM_PROVIDER=anthropic ve ANTHROPIC_API_KEY=sk-ant-..."
            )
        if tools is None:
            tools = load_index_tools()
        answer = await _ask_anthropic(asked, tools, settings, system)
        return await _translate(answer, lang, settings) if use_pivot else answer
    if not settings.llm_base_url:
        return (
            "LLM yapılandırılmamış. Canlı ajan için ya Claude API "
            "(ETKI_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY) ya da "
            "OpenAI-uyumlu (ETKI_LLM_BASE_URL=http://localhost:11434/v1, Ollama)."
        )
    if tools is None:
        tools = load_index_tools()
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": asked},
    ]
    async with httpx.AsyncClient(timeout=180.0) as client:
        for _ in range(6):
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "tools": _TOOL_SCHEMA,
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            messages.append(message)
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                answer = message.get("content", "") or "(boş yanıt)"
                return await _translate(answer, lang, settings) if use_pivot else answer
            for call in tool_calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                result = _dispatch(tools, name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
    return "Yanıt üretilemedi (araç çağrısı döngüsü limiti aşıldı)."


def main() -> None:
    question = " ".join(sys.argv[1:]) or "Baseline özetini ver ve kaç madde kapsam dışı söyle."
    print(asyncio.run(ask(question)))


if __name__ == "__main__":
    main()
