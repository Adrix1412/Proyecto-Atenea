"""OS operations are mocked. These tests do not launch desktop programs."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from alicia_core.config import LLMConfig
from alicia_desktop.config import DesktopConfig, load_config, save_config
from alicia_desktop.factory import build_service
from alicia_desktop.launcher import AppLauncher, validate_command


@pytest.mark.parametrize(
    "command",
    [
        "echo injected",
        ["editor"],
        ["/bin/sh", "-c", "evil"],
        ["/tmp/run.cmd"],
        ["/tmp/app.lnk"],
        ["/tmp/app", "a\x00b"],
    ],
)
def test_unsafe_commands_rejected(command: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        validate_command(command)


def test_launcher_never_uses_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = tmp_path / "editor"
    executable.touch()
    executable.chmod(0o700)
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    launcher = AppLauncher({"editor": [str(executable)]})
    launcher.launch("editor")
    assert popen.call_args.kwargs["shell"] is False
    assert popen.call_args.args[0] == [str(executable)]
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL


def test_config_roundtrip_does_not_preserve_secrets(tmp_path: Path) -> None:
    cfg = DesktopConfig()
    p = tmp_path / "config.yaml"
    save_config(p, cfg)
    assert load_config(p) == cfg
    with pytest.raises(ValidationError):
        DesktopConfig.model_validate({"llm": {"api_key": "do-not-store"}})


def test_cloud_endpoint_override_rejected() -> None:
    with pytest.raises(ValidationError):
        DesktopConfig.model_validate({"llm": {"provider": "gemini", "base_url": "https://untrusted.test"}})


def test_desktop_tool_authorizes_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = tmp_path / "editor"
    launcher = AppLauncher({"editor": [str(executable)]})
    launched: list[str] = []
    monkeypatch.setattr(launcher, "launch", lambda name: launched.append(name) or "iniciado")
    config = DesktopConfig(llm=LLMConfig(model="fixture", base_url="https://ollama.example.test"))
    service = build_service(config, tmp_path / "config.yaml", launcher, lambda name, app: False)
    try:
        registry = service.client.registry
        assert "inválidos" in registry.execute("abrir_app", {"app_name": "desconocida"})
        assert "denegada" in registry.execute("abrir_app", {"app_name": "editor"})
        assert not launched
    finally:
        service.client.close()
