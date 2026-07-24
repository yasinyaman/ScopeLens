"""Anthropic Claude API LLM adapter + provider selection (factory). No live key needed."""

from etki.adapters.llm_anthropic import AnthropicLLMClient, _strip_json_fences
from etki.adapters.llm_openai import OpenAICompatibleLLMClient
from etki.adapters.registry import build_llm_client
from etki.config import Settings


def test_strip_json_fences():
    assert _strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_json_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_factory_openai_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # no endpoint -> None (falls back to the heuristic path)
    assert build_llm_client(Settings(llm_provider="openai", llm_base_url=None)) is None
    # endpoint present -> OpenAI-compatible client
    client = build_llm_client(Settings(llm_provider="openai", llm_base_url="http://x/v1"))
    assert isinstance(client, OpenAICompatibleLLMClient)


def test_factory_anthropic_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # no key -> None
    assert build_llm_client(Settings(llm_provider="anthropic", anthropic_api_key=None)) is None
    # key present -> Anthropic client
    client = build_llm_client(
        Settings(llm_provider="anthropic", anthropic_api_key="sk-ant-test")
    )
    assert isinstance(client, AnthropicLLMClient)


def test_factory_anthropic_reads_env_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    client = build_llm_client(Settings(llm_provider="anthropic", anthropic_api_key=None))
    assert isinstance(client, AnthropicLLMClient)


async def test_complete_json_parses_fenced_response(monkeypatch):
    client = AnthropicLLMClient(api_key="sk-ant-test")

    class _Block:
        type = "text"
        text = '```json\n{"items": [{"id": "1"}]}\n```'

    class _Message:
        content = [_Block()]

    async def fake_create(**kwargs):
        return _Message()

    monkeypatch.setattr(client._client.messages, "create", fake_create)
    out = await client.complete_json(system="sys", user="metin")
    assert out == {"items": [{"id": "1"}]}


async def test_system_prompt_is_cache_controlled(monkeypatch):
    """The stable system prefix (preamble + fixed RESPONSE instruction) is sent as
    a cache-controlled content block, so a reused client reads it from cache across
    a burst of calls; the varying `user` turn stays uncached after the breakpoint.
    Byte-neutral by API contract — this only pins that we emit cache_control."""
    client = AnthropicLLMClient(api_key="sk-ant-test")
    captured: dict = {}

    class _Message:
        content = [type("_B", (), {"type": "text", "text": '{"ok": true}'})()]

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _Message()

    monkeypatch.setattr(client._client.messages, "create", fake_create)
    await client.complete_json(system="PREAMBLE", user="talep")

    system = captured["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "PREAMBLE" in system[0]["text"]
    assert "one valid JSON object" in system[0]["text"]  # the fixed instruction is cached too
    assert captured["messages"] == [{"role": "user", "content": "talep"}]  # varying, uncached
