"""Typed tools reject invalid input before domain checks, approval and effects."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from alicia_core.adapters.providers import ProviderCodec
from alicia_core.config import LLMConfig
from alicia_core.permissions import Risk
from alicia_core.tools import ToolRegistry, TypedTool


class EditArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str = Field(min_length=1, max_length=20)
    new_title: str = Field(min_length=1, max_length=40)


def test_schema_matches_two_argument_contract() -> None:
    tool = TypedTool("rename", "Renombrar", EditArgs, lambda args: args.new_title)
    assert tool.schema()["additionalProperties"] is False
    assert tool.schema()["required"] == ["document_id", "new_title"]
    assert set(tool.schema()["properties"]) == {"document_id", "new_title"}


@pytest.mark.parametrize(
    "args",
    [
        {"document_id": "a"},
        {"document_id": "a", "new_title": "b", "extra": "ignored"},
        {"document_id": 12, "new_title": "b"},
        {"document_id": "a", "new_title": ""},
    ],
)
def test_schema_validation_runs_before_policy(args: dict[str, object]) -> None:
    effects: list[str] = []
    approvals: list[str] = []
    tool = TypedTool(
        "rename",
        "Renombrar",
        EditArgs,
        lambda value: effects.append(value.new_title) or "ok",
        authorize=lambda value: approvals.append(value.document_id) or True,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    assert ToolRegistry((tool,)).execute("rename", args).startswith("Error")
    assert not effects and not approvals


def test_domain_rejection_and_missing_approval_fail_closed() -> None:
    effects: list[str] = []

    def policy(value: EditArgs) -> bool:
        return value.document_id == "allowed"

    tool = TypedTool(
        "rename",
        "Renombrar",
        EditArgs,
        lambda value: effects.append(value.new_title) or "ok",
        domain_check=policy,
        authorize=lambda value: False,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    registry = ToolRegistry((tool,))
    assert "inválidos" in registry.execute("rename", {"document_id": "other", "new_title": "x"})
    assert "denegada" in registry.execute("rename", {"document_id": "allowed", "new_title": "x"})
    assert not effects
    with pytest.raises(ValueError):
        TypedTool(
            "bad",
            "Sin permiso",
            EditArgs,
            lambda value: "ok",
            requires_confirmation=True,
            risk=Risk.REVERSIBLE,
        )
    with pytest.raises(ValueError):
        TypedTool(
            "bad",
            "Riesgo falso",
            EditArgs,
            lambda value: "ok",
            authorize=lambda value: True,
            requires_confirmation=True,
            risk=Risk.READ,
        )


def test_success_and_policy_exception_handling() -> None:
    result = TypedTool(
        "rename",
        "Renombrar",
        EditArgs,
        lambda value: value.new_title,
        authorize=lambda value: True,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    assert ToolRegistry((result,)).execute("rename", {"document_id": "a", "new_title": "nuevo"}) == "nuevo"

    def unavailable(value: EditArgs) -> bool:
        raise RuntimeError("private policy detail")

    blocked = TypedTool(
        "rename",
        "Renombrar",
        EditArgs,
        lambda value: "never",
        authorize=unavailable,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    assert "private policy detail" not in ToolRegistry((blocked,)).execute(
        "rename", {"document_id": "a", "new_title": "nuevo"}
    )


@pytest.mark.parametrize("provider", ["ollama", "anthropic", "gemini"])
def test_typed_schema_is_advertised_to_providers(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value")
    monkeypatch.setenv("GEMINI_API_KEY", "test-value")
    tool = TypedTool("rename", "Renombrar", EditArgs, lambda value: "ok")
    codec = ProviderCodec(
        LLMConfig(
            provider=provider, model="fixture", base_url="https://ollama.test" if provider == "ollama" else ""
        ),
        ToolRegistry((tool,)),
    )
    _, payload, _ = codec.request([], "system")
    if provider == "ollama":
        definitions = payload["tools"]
        assert isinstance(definitions, list)
        schema = definitions[0]["function"]["parameters"]
    elif provider == "anthropic":
        definitions = payload["tools"]
        assert isinstance(definitions, list)
        schema = definitions[0]["input_schema"]
    else:
        definitions = payload["tools"]
        assert isinstance(definitions, list)
        schema = definitions[0]["functionDeclarations"][0]["parametersJsonSchema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"document_id", "new_title"}
