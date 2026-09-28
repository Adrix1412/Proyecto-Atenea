"""REST codecs keep provider-specific envelopes out of orchestration."""

from dataclasses import dataclass
from urllib.parse import quote

from alicia_core.config import LLMConfig
from alicia_core.domain import Message
from alicia_core.errors import ProviderError
from alicia_core.jsonutil import items, obj, string
from alicia_core.tools import ToolRegistry


@dataclass(frozen=True)
class Call:
    name: str
    arguments: dict[str, object]
    identifier: str = ""


@dataclass(frozen=True)
class Completion:
    text: str
    calls: tuple[Call, ...]
    raw: dict[str, object]


class ProviderCodec:
    def __init__(self, config: LLMConfig, registry: ToolRegistry) -> None:
        self.cfg = config
        self.registry = registry

    def initial(self, history: tuple[Message, ...], user: str) -> list[dict[str, object]]:
        messages = (*history, Message("user", user))
        if self.cfg.provider == "gemini":
            return [
                {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                for m in messages
            ]
        return [{"role": m.role, "content": m.content} for m in messages]

    def request(
        self, messages: list[dict[str, object]], prompt: str
    ) -> tuple[str, dict[str, object], dict[str, str]]:
        tools = self.registry.tools
        cfg = self.cfg
        if cfg.provider == "ollama":
            payload: dict[str, object] = {
                "model": cfg.model,
                "stream": False,
                "messages": [{"role": "system", "content": prompt}, *messages],
                "options": {"temperature": cfg.temperature, "num_predict": cfg.max_output_tokens},
            }
            if tools:
                payload["tools"] = [
                    {
                        "type": "function",
                        "function": {"name": t.name, "description": t.description, "parameters": t.schema()},
                    }
                    for t in tools
                ]
            return cfg.base_url + "/api/chat", payload, {}
        if cfg.provider == "anthropic":
            payload = {
                "model": cfg.model,
                "system": prompt,
                "messages": messages,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_output_tokens,
            }
            if tools:
                payload["tools"] = [
                    {"name": t.name, "description": t.description, "input_schema": t.schema()} for t in tools
                ]
            return (
                "https://api.anthropic.com/v1/messages",
                payload,
                {"x-api-key": cfg.key(), "anthropic-version": "2023-06-01"},
            )
        payload = {
            "contents": messages,
            "systemInstruction": {"parts": [{"text": prompt}]},
            "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_output_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parametersJsonSchema": t.schema()}
                        for t in tools
                    ]
                }
            ]
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(cfg.model, safe="")
            + ":generateContent"
        )
        return url, payload, {"x-goog-api-key": cfg.key()}

    def parse(self, data: dict[str, object]) -> Completion:
        calls: list[Call] = []
        if self.cfg.provider == "ollama":
            if data.get("done_reason") == "length":
                raise ProviderError("El proveedor truncó la respuesta; reduzca la consulta.")
            raw = obj(data.get("message"))
            for value in items(raw.get("tool_calls", [])):
                fn = obj(obj(value).get("function"))
                calls.append(Call(string(fn.get("name")), obj(fn.get("arguments"))))
            return Completion(string(raw.get("content", "")), tuple(calls), raw)
        if self.cfg.provider == "anthropic":
            if data.get("stop_reason") in ("max_tokens", "refusal"):
                raise ProviderError("El proveedor no entregó una respuesta completa.")
            blocks = [obj(v) for v in items(data.get("content"))]
            for b in blocks:
                if b.get("type") == "tool_use":
                    calls.append(Call(string(b.get("name")), obj(b.get("input")), string(b.get("id"))))
            text = "".join(string(b.get("text")) for b in blocks if b.get("type") == "text")
            return Completion(text, tuple(calls), {"role": "assistant", "content": blocks})
        candidates = items(data.get("candidates", []))
        if not candidates:
            raise ProviderError("Gemini no devolvió candidatos; revise las restricciones del modelo.")
        candidate = obj(candidates[0])
        if candidate.get("finishReason", "STOP") != "STOP":
            raise ProviderError("Gemini no entregó una respuesta completa.")
        raw = obj(candidate.get("content"))
        parts = [obj(p) for p in items(raw.get("parts"))]
        for part in parts:
            if "functionCall" in part:
                fn = obj(part["functionCall"])
                calls.append(Call(string(fn.get("name")), obj(fn.get("args", {})), string(fn.get("id", ""))))
        text = "".join(string(p["text"]) for p in parts if "text" in p and not p.get("thought"))
        return Completion(text, tuple(calls), raw)

    def append_results(
        self, messages: list[dict[str, object]], completion: Completion, results: list[str]
    ) -> None:
        # Preserve Gemini thought signatures / opaque parts exactly as returned.
        messages.append(completion.raw)
        if self.cfg.provider == "ollama":
            messages.extend(
                {"role": "tool", "tool_name": c.name, "content": r}
                for c, r in zip(completion.calls, results, strict=True)
            )
        elif self.cfg.provider == "anthropic":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": c.identifier, "content": r}
                        for c, r in zip(completion.calls, results, strict=True)
                    ],
                }
            )
        else:
            responses: list[dict[str, object]] = []
            for call, result in zip(completion.calls, results, strict=True):
                response: dict[str, object] = {"name": call.name, "response": {"result": result}}
                if call.identifier:
                    response["id"] = call.identifier
                responses.append({"functionResponse": response})
            messages.append({"role": "user", "parts": responses})
