"""Provider contract tests use HTTP fixtures; no real API keys or network calls."""

import json

import httpx
import pytest

from alicia_core.adapters.http_transport import HTTPTransport
from alicia_core.config import LLMConfig
from alicia_core.domain import Message
from alicia_core.errors import ProviderError
from alicia_core.llm import LLMClient
from alicia_core.tools import Tool, ToolRegistry


@pytest.mark.parametrize("provider", ["ollama", "anthropic", "gemini"])
def test_provider_tool_round_trip(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-value")
    received = []
    executed = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        received.append(payload)
        if len(received) == 1:
            if provider == "ollama":
                body = {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": "lookup", "arguments": {"query": "hello"}}}],
                    }
                }
            elif provider == "anthropic":
                body = {
                    "content": [
                        {"type": "tool_use", "id": "call-1", "name": "lookup", "input": {"query": "hello"}}
                    ]
                }
            else:
                body = {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "lookup",
                                            "args": {"query": "hello"},
                                            "id": "call-1",
                                        },
                                        "thoughtSignature": "opaque-signature",
                                    }
                                ],
                            }
                        }
                    ]
                }
        elif provider == "ollama":
            assert payload["messages"][-1]["tool_name"] == "lookup"
            body = {"message": {"role": "assistant", "content": "Listo"}}
        elif provider == "anthropic":
            assert payload["messages"][-1]["content"][0]["tool_use_id"] == "call-1"
            body = {"content": [{"type": "text", "text": "Listo"}]}
        else:
            assert payload["contents"][-2]["parts"][0]["thoughtSignature"] == "opaque-signature"
            assert payload["contents"][-1]["parts"][0]["functionResponse"]["id"] == "call-1"
            body = {"candidates": [{"content": {"role": "model", "parts": [{"text": "Listo"}]}}]}
        return httpx.Response(200, json=body)

    cfg = LLMConfig(
        provider=provider,
        model="fixture-model",
        base_url="https://ollama.example.test" if provider == "ollama" else "",
    )
    registry = ToolRegistry((Tool("lookup", "Look up", "query", lambda v: executed.append(v) or "result"),))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = LLMClient(cfg, registry, HTTPTransport(10, http))
        assert (
            client.chat((Message("user", "anterior"), Message("assistant", "respuesta")), "hola") == "Listo"
        )
    assert executed == ["hello"]
    assert len(received) == 2


def test_loop_budget_and_duplicate_side_effect_suppression() -> None:
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "open", "arguments": {"name": "editor"}}}],
                }
            },
        )

    registry = ToolRegistry((Tool("open", "Open", "name", lambda v: called.append(v) or "started"),))
    cfg = LLMConfig(model="fixture", base_url="https://ollama.example.test", max_tool_rounds=2)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ProviderError, match="límite"):
            LLMClient(cfg, registry, HTTPTransport(10, http)).chat((), "hola")
    assert called == ["editor"]


def test_excessive_parallel_calls_run_nothing() -> None:
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "tool_calls": [{"function": {"name": "open", "arguments": {"name": "editor"}}}] * 9
                }
            },
        )

    registry = ToolRegistry((Tool("open", "Open", "name", lambda v: called.append(v) or "started"),))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ProviderError):
            LLMClient(
                LLMConfig(model="fixture", base_url="https://ollama.example.test"),
                registry,
                HTTPTransport(10, http),
            ).chat((), "hola")
    assert not called


@pytest.mark.parametrize(
    "status,body",
    [
        (401, b"private-upstream-error"),
        (302, b""),
        (200, b"invalid-json"),
        (200, b"[]"),
        (200, b"x" * 2_000_001),
    ],
)
def test_transport_rejects_bad_responses_without_leaking(status: int, body: bytes) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))
    ) as http:
        with pytest.raises(ProviderError) as error:
            HTTPTransport(10, http).post("https://example.test", {}, {})
    assert "private-upstream-error" not in str(error.value)


def test_timeout_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret diagnostic", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ProviderError, match="tiempo") as error:
            HTTPTransport(10, http).post("https://example.test", {}, {})
    assert "secret diagnostic" not in str(error.value)


def test_gemini_missing_candidate_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as http:
        with pytest.raises(ProviderError, match="candidatos"):
            LLMClient(LLMConfig(provider="gemini", model="fixture"), transport=HTTPTransport(10, http)).chat(
                (), "hola"
            )


def test_gemini_interactions_text_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    received: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        assert request.url.path == "/v1beta/interactions"
        return httpx.Response(
            200,
            json={
                "id": "int-fixture",
                "status": "completed",
                "steps": [
                    {"type": "user_input", "status": "done", "content": [{"type": "text", "text": "hola"}]},
                    {"type": "model_output", "status": "done", "content": [{"type": "text", "text": "Hola"}]},
                ],
            },
        )

    cfg = LLMConfig(provider="gemini", model="gemini-3.8-flash", gemini_api="interactions")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert LLMClient(cfg, transport=HTTPTransport(10, http)).chat((), "hola") == "Hola"
    assert received[0]["model"] == "gemini-3.8-flash"
    assert received[0]["input"].endswith("Usuario: hola")
    assert "Alicia" in str(received[0]["system_instruction"])
