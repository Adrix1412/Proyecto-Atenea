"""Migration tests use synthetic settings; private user configuration is never loaded here."""

from pathlib import Path
from zipfile import ZipFile

import yaml

from alicia_desktop.config import DesktopConfig
from alicia_desktop.migrate_legacy_config import _read_source, convert_legacy


def test_migration_keeps_safe_apps_and_discards_credentials(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "editor"
    executable.touch()
    monkeypatch.setattr("alicia_desktop.migrate_legacy_config.shutil.which", lambda name: str(executable))
    source = {
        "llm": {
            "provider": "gemini",
            "gemini_model": "model-real-en-tu-cuenta",
            "api_key": "PRIVATE_EXAMPLE_VALUE",
            "system_prompt": "PRIVATE_PROMPT_VALUE",
            "timeout_sec": 30.0,
        },
        "apps": {"editor": [str(executable)], "other": "editor"},
        "avatar": {"enabled": True, "host": "localhost", "port": 8001},
        "audio": {"silence_timeout_sec": 30},
        "memory": {"db_path": "private-old.db"},
    }
    result, skipped = convert_legacy(source)
    assert skipped == ()
    assert result["apps"] == {"editor": [str(executable)], "other": [str(executable)]}
    assert result["memory_path"] != "private-old.db"
    assert result["avatar"] == {"enabled": True, "host": "127.0.0.1", "port": 8001}
    assert "PRIVATE_EXAMPLE_VALUE" not in yaml.safe_dump(result)
    assert "PRIVATE_PROMPT_VALUE" not in yaml.safe_dump(result)
    config = DesktopConfig.model_validate(result)
    assert config.llm.api_key_env == "GEMINI_API_KEY"


def test_unresolved_commands_and_scripts_are_not_imported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("alicia_desktop.migrate_legacy_config.shutil.which", lambda name: None)
    config, skipped = convert_legacy(
        {
            "apps": {
                "missing": "unavailable",
                "script": [str(tmp_path / "launch.cmd")],
                "shell": ["C:\\Windows\\System32\\cmd.exe"],
            }
        }
    )
    assert config["apps"] == {}
    assert skipped == ("missing", "script", "shell")


def test_private_zip_is_read_without_extracting_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "legacy.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("alicia/config.yaml", "apps: {editor: /usr/bin/editor}\nllm: {api_key: secret}\n")
        archive.writestr("alicia/vts_token.txt", "private-token")
    source = _read_source(archive_path)
    result, _ = convert_legacy(source)
    assert "secret" not in yaml.safe_dump(result)
    assert not (tmp_path / "vts_token.txt").exists()


def test_existing_configuration_is_not_overwritten(tmp_path: Path, monkeypatch) -> None:
    from alicia_desktop.migrate_legacy_config import main

    source = tmp_path / "old.yaml"
    source.write_text("apps: {}\n", encoding="utf-8")
    destination = tmp_path / "config.yaml"
    destination.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["migrate", str(source), "--output", str(destination), "--write"])
    assert main() == 1
    assert destination.read_text(encoding="utf-8") == "unchanged"
