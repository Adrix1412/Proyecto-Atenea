"""Desktop settings separate audio/device/process configuration from the core."""

import ipaddress
import os
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from alicia_core.config import LLMConfig, StrictModel, read_yaml
from alicia_core.errors import ConfigurationError


class STTConfig(StrictModel):
    model_size: str = Field(default="small", min_length=1, max_length=500)
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: Literal[
        "default",
        "auto",
        "int8",
        "int8_float16",
        "int8_float32",
        "int8_bfloat16",
        "int16",
        "float16",
        "bfloat16",
        "float32",
    ] = "int8"
    language: str = Field(default="es", pattern=r"^[a-z]{2,3}$")


class TTSConfig(StrictModel):
    voice: str = Field(default="es-AR-ElenaNeural", min_length=1, max_length=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.5)
    volume: int = Field(default=100, ge=0, le=100)
    sample_rate: int = Field(default=24000, ge=8000, le=48000)


class AudioConfig(StrictModel):
    input_device: int | str | None = None
    output_device: int | str | None = None
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    max_recording_sec: int = Field(default=30, ge=1, le=120)


class AvatarConfig(StrictModel):
    enabled: bool = False
    host: str = ""
    port: int = Field(default=8001, ge=1, le=65535)

    @model_validator(mode="after")
    def local_only(self) -> "AvatarConfig":
        if self.enabled and not ipaddress.ip_address(self.host).is_loopback:
            raise ValueError("VTube Studio debe estar en una dirección loopback.")
        return self


class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = Field(default="logs/alicia.log", min_length=1, max_length=4096)


class DesktopConfig(StrictModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    search_enabled: bool = False
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    avatar: AvatarConfig = Field(default_factory=AvatarConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    hotkey: str = "f9"
    memory_path: str = Field(default="data/alicia_memory.db", min_length=1, max_length=4096)
    apps: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("hotkey")
    @classmethod
    def function_key(cls, value: str) -> str:
        if value not in {f"f{i}" for i in range(1, 13)}:
            raise ValueError("Use una tecla de f1 a f12.")
        return value

    @field_validator("apps")
    @classmethod
    def commands(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        from .launcher import validate_command

        for name, command in value.items():
            if not name or len(name) > 80 or not all(c.isalnum() or c in "_-" for c in name):
                raise ValueError("Nombre de aplicación inválido.")
            validate_command(command)
        return value


def load_config(path: Path) -> DesktopConfig:
    try:
        return DesktopConfig.model_validate(read_yaml(path))
    except (ValidationError, ValueError) as exc:
        raise ConfigurationError(
            "Configuración inválida. Revise la plantilla y elimine secretos del YAML."
        ) from exc


def save_config(path: Path, config: DesktopConfig) -> None:
    """Atomic replacement avoids half-written configuration after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".alicia-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(config.model_dump(), stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def resolve_path(config_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_path.resolve().parent / path
