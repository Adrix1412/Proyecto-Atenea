"""Strict configuration. Secrets are resolved only from the process environment."""

import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import ConfigurationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class LLMConfig(StrictModel):
    provider: Literal["ollama", "anthropic", "gemini"] = "ollama"
    model: str = Field(default="", max_length=150)
    base_url: str = ""
    api_key_env: str = ""
    gemini_api: Literal["generate_content", "interactions"] = "generate_content"
    temperature: float = Field(default=0.8, ge=0, le=1)
    timeout_sec: float = Field(default=45.0, ge=1, le=180)
    max_history_turns: int = Field(default=12, ge=1, le=50)
    max_context_chars: int = Field(default=48000, ge=16000, le=200000)
    max_output_tokens: int = Field(default=2048, ge=128, le=4096)
    max_tool_rounds: int = Field(default=4, ge=0, le=6)
    max_tool_calls: int = Field(default=8, ge=0, le=16)
    system_prompt: str = Field(default="", max_length=12000)

    @field_validator("model")
    @classmethod
    def model_identifier(cls, value: str) -> str:
        if value and not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value):
            raise ValueError("Identificador de modelo inválido.")
        return value

    @field_validator("api_key_env")
    @classmethod
    def env_name(cls, value: str) -> str:
        if value and not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
            raise ValueError("Nombre de variable de entorno inválido.")
        return value

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value: str) -> str:
        if not value:
            return value
        u = urlsplit(value)
        if (
            u.scheme not in ("http", "https")
            or not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
            or u.path not in ("", "/")
        ):
            raise ValueError("Endpoint inválido.")
        if u.scheme == "http" and u.hostname not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("Los endpoints remotos requieren HTTPS.")
        return value.rstrip("/")

    @model_validator(mode="after")
    def provider_endpoint(self) -> "LLMConfig":
        if self.provider != "ollama" and self.base_url:
            raise ValueError("Las APIs cloud usan endpoints fijos; omita base_url.")
        if self.provider != "gemini" and self.gemini_api != "generate_content":
            raise ValueError("gemini_api solo se admite con Gemini.")
        return self

    def key(self) -> str:
        name = self.api_key_env or {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}.get(
            self.provider, ""
        )
        value = os.environ.get(name, "").strip()
        if self.provider != "ollama" and not value:
            raise ConfigurationError(f"Falta la variable de entorno {name}.")
        return value

    def ready(self) -> None:
        if not self.model:
            raise ConfigurationError("Configure llm.model con un modelo disponible en su proveedor.")
        if self.provider == "ollama" and not self.base_url:
            raise ConfigurationError("Configure llm.base_url con el endpoint de su servidor Ollama.")
        self.key()


class CoreConfig(StrictModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    search_enabled: bool = False


def read_yaml(path: Path) -> object:
    try:
        if path.stat().st_size > 65536:
            raise ConfigurationError("El YAML excede 64 KiB.")
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        raise ConfigurationError("No se pudo leer el YAML de configuración.") from exc


def load_core_config(path: Path) -> CoreConfig:
    try:
        return CoreConfig.model_validate(read_yaml(path))
    except ValidationError as exc:
        # Do not stringify ValidationError: it embeds rejected input values.
        raise ConfigurationError("Configuración inválida; revise config.example.yaml.") from exc
