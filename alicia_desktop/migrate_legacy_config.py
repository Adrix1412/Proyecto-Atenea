"""Import desktop settings from a private legacy YAML or ZIP without copying secrets."""

import argparse
import ntpath
import os
import shutil
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import yaml
from pydantic import ValidationError

from .config import DesktopConfig, save_config
from .launcher import DENIED, validate_command

MAX_SOURCE_BYTES = 65536


def _read_source(path: Path) -> dict[str, object]:
    if path.suffix.lower() == ".zip":
        with ZipFile(path) as archive:
            matches = [name for name in archive.namelist() if name in ("alicia/config.yaml", "config.yaml")]
            if len(matches) != 1 or archive.getinfo(matches[0]).file_size > MAX_SOURCE_BYTES:
                raise ValueError("El ZIP no contiene un único config.yaml compatible.")
            raw = archive.read(matches[0])
    else:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("La configuración supera el tamaño permitido.")
        raw = path.read_bytes()
    value = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("La configuración antigua no es un objeto YAML.")
    return value


def _section(source: dict[str, object], name: str) -> dict[str, object]:
    value = source.get(name)
    return value if isinstance(value, dict) else {}


def _absolute(command: str) -> bool:
    if command.startswith("\\\\"):
        return False
    return os.path.isabs(command) or ntpath.isabs(command)


def convert_legacy(source: dict[str, object]) -> tuple[dict[str, object], tuple[str, ...]]:
    """Return a secret-free configuration and the app names that require manual review."""
    result: dict[str, object] = DesktopConfig().model_dump()
    llm = _section(source, "llm")
    provider = llm.get("provider", "ollama")
    if provider not in ("ollama", "gemini", "anthropic"):
        raise ValueError("Proveedor antiguo no compatible.")
    model_key = {"ollama": "model", "gemini": "gemini_model", "anthropic": "anthropic_model"}[provider]
    llm_config = _section(result, "llm")
    llm_config["provider"] = provider
    llm_config["model"] = llm.get(model_key, "")
    llm_config["base_url"] = llm.get("base_url", "") if provider == "ollama" else ""
    llm_config["api_key_env"] = {"ollama": "", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[
        provider
    ]
    for field in ("temperature", "timeout_sec", "max_history_turns"):
        if field in llm:
            llm_config[field] = llm[field]
    result["llm"] = llm_config

    for name, fields in (
        ("stt", ("model_size", "device", "compute_type", "language")),
        ("tts", ("voice", "speed", "volume", "sample_rate")),
        ("audio", ("input_device", "output_device", "sample_rate")),
        ("logging", ("level", "file")),
        ("avatar", ("enabled", "host", "port")),
    ):
        target = _section(result, name)
        original = _section(source, name)
        for field in fields:
            if field in original:
                target[field] = original[field]
        if name == "avatar" and target.get("host") == "localhost":
            target["host"] = "127.0.0.1"
        result[name] = target
    audio = _section(result, "audio")
    old_timeout = _section(source, "audio").get("silence_timeout_sec")
    if old_timeout is not None:
        audio["max_recording_sec"] = old_timeout
    result["audio"] = audio
    result["hotkey"] = _section(source, "hotkey").get("key", "f9")

    apps: dict[str, list[str]] = {}
    skipped: list[str] = []
    for name, command in _section(source, "apps").items():
        if not isinstance(name, str) or not name or not all(c.isalnum() or c in "_-" for c in name):
            raise ValueError("Existe un nombre de aplicación inválido.")
        parts: list[str] | None = None
        if isinstance(command, str):
            executable = command if _absolute(command) else shutil.which(command)
            if executable:
                parts = [executable]
        elif isinstance(command, list) and len(command) == 1 and isinstance(command[0], str):
            parts = command.copy()
        if parts is None or not _absolute(parts[0]):
            skipped.append(name)
            continue
        try:
            if (
                ntpath.splitext(parts[0])[1].lower()
                in {".bat", ".cmd", ".ps1", ".lnk", ".vbs", ".js", ".py", ".sh"}
                or ntpath.splitext(ntpath.basename(parts[0]))[0].lower() in DENIED
            ):
                raise ValueError("No se admiten scripts ni intérpretes.")
            if os.name == "nt" or os.path.isabs(parts[0]):
                validate_command(parts)
            apps[name] = parts
        except ValueError:
            skipped.append(name)
    result["apps"] = apps
    return result, tuple(skipped)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra la configuración privada de Alicia sin claves.")
    parser.add_argument("source", type=Path, help="Ruta al config.yaml antiguo o al ZIP original")
    parser.add_argument("--output", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--write", action="store_true", help="Escribe la configuración nueva; por defecto simula"
    )
    args = parser.parse_args()
    try:
        config, skipped = convert_legacy(_read_source(args.source))
        print(f"Aplicaciones conservadas: {len(_section(config, 'apps'))}; por revisar: {len(skipped)}.")
        if skipped:
            print("Por revisar: " + ", ".join(skipped))
        if not args.write:
            print("Simulación: no se escribió ningún archivo.")
            return 0
        if args.output.exists():
            raise ValueError("El archivo de destino ya existe; elige otra ruta.")
        desktop = DesktopConfig.model_validate(config)
        save_config(args.output, desktop)
        print("Configuración nueva guardada sin claves ni historial.")
        return 0
    except (OSError, ValueError, ValidationError, UnicodeError, yaml.YAMLError, BadZipFile, KeyError):
        print("No se completó la migración; revisa origen, formato y rutas en este sistema.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
