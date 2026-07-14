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
