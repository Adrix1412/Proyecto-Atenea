"""Regression checks for conversation atomicity, validation and desktop isolation."""

import ast
import sqlite3
from pathlib import Path

import pytest

from alicia_core.adapters.sqlite_memory import SQLiteMemory
from alicia_core.config import load_core_config
from alicia_core.domain import Message
from alicia_core.errors import ConfigurationError, ConversationConflict, ProviderError, StorageError
from alicia_core.service import ConversationService
from alicia_core.tools import Tool, ToolRegistry


class EchoClient:
    def chat(self, history: tuple[Message, ...], user_message: str) -> str:
        return "Respuesta verificable"

    def close(self) -> None:
        pass


def test_core_has_no_desktop_imports() -> None:
    forbidden = {"alicia_desktop", "PySide6", "pynput", "sounddevice", "faster_whisper", "edge_tts", "pydub"}
    for path in Path("alicia_core").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not {n.name.split(".")[0] for n in node.names} & forbidden
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden


def test_atomic_turn_and_order(tmp_path: Path) -> None:
    repo = SQLiteMemory(tmp_path / "memory.db")
    service = ConversationService(repo, EchoClient())
    assert service.reply("Hola") == "Respuesta verificable"
    assert repo.snapshot(1).messages == (
        Message("user", "Hola"),
        Message("assistant", "Respuesta verificable"),
    )
    assert repo.snapshot(1).revision == 1


def test_database_failure_rolls_back_whole_turn(tmp_path: Path) -> None:
    repo = SQLiteMemory(tmp_path / "memory.db")
    with sqlite3.connect(repo.db_path) as c:
        c.execute(
            "CREATE TRIGGER fail_assistant BEFORE INSERT ON messages WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT, 'test'); END;"
        )
    with pytest.raises(StorageError):
        repo.append_turn("pregunta", "respuesta", 0)
    assert repo.snapshot(1).messages == ()
    assert repo.snapshot(1).revision == 0


def test_conflict_and_clear_do_not_overwrite(tmp_path: Path) -> None:
    a = SQLiteMemory(tmp_path / "memory.db")
    b = SQLiteMemory(tmp_path / "memory.db")
    before = b.snapshot(1)
    a.append_turn("uno", "dos", 0)
    with pytest.raises(ConversationConflict):
        b.append_turn("tres", "cuatro", before.revision)
    a.clear()
    with pytest.raises(ConversationConflict):
        b.append_turn("tres", "cuatro", 1)
    assert a.snapshot(1).messages == ()


def test_failure_does_not_store_user_prompt(tmp_path: Path) -> None:
    class Failing(EchoClient):
        def chat(self, history: tuple[Message, ...], user_message: str) -> str:
            raise ProviderError("unavailable")

    repo = SQLiteMemory(tmp_path / "memory.db")
    with pytest.raises(ProviderError):
        ConversationService(repo, Failing()).reply("Hola")
    assert not repo.snapshot(1).messages


@pytest.mark.parametrize("text", ["", " ", "x" * 16001, "a\x00b"])
def test_invalid_input_never_reaches_model(tmp_path: Path, text: str) -> None:
    class Never(EchoClient):
        def chat(self, history: tuple[Message, ...], user_message: str) -> str:
            pytest.fail("provider must not run")

    with pytest.raises(ValueError):
        ConversationService(SQLiteMemory(tmp_path / "m.db"), Never()).reply(text)


@pytest.mark.parametrize(
    "arguments", [{"app": "editor", "command": "evil"}, {"app": ["editor"]}, {"app": "unknown"}, {}]
)
def test_tools_reject_invalid_arguments(arguments: dict[str, object]) -> None:
    calls = []
    registry = ToolRegistry((Tool("open", "Open", "app", lambda v: calls.append(v) or "ok", ("editor",)),))
    assert registry.execute("open", arguments).startswith("Error")
    assert not calls


def test_sensitive_tools_fail_closed() -> None:
    calls = []
    tool = Tool(
        "open", "Open", "app", lambda v: calls.append(v) or "ok", ("editor",), requires_confirmation=True
    )
    assert "denegada" in ToolRegistry((tool,)).execute("open", {"app": "editor"})
    assert not calls
    assert ToolRegistry((tool,), lambda n, v: True).execute("open", {"app": "editor"}) == "ok"
    assert calls == ["editor"]


def test_unknown_tool_never_executes() -> None:
    assert "no permitida" in ToolRegistry().execute("shell", {"command": "whoami"})


def test_yaml_secret_is_rejected_without_echo(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("llm:\n  api_key: credential-do-not-echo\n")
    with pytest.raises(ConfigurationError) as error:
        load_core_config(path)
    assert "credential-do-not-echo" not in str(error.value)


def test_desktop_legacy_import_is_read_only_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE exchanges(id INTEGER PRIMARY KEY, timestamp REAL, role TEXT, content TEXT)")
        c.executemany(
            "INSERT INTO exchanges VALUES(?,?,?,?)",
            [(1, 1.0, "user", "hola"), (2, 2.0, "assistant", "respuesta")],
        )
    before = source.read_bytes()
    repo = SQLiteMemory(tmp_path / "new.db")
    assert repo.import_legacy(source, dry_run=True) == 2
    assert not repo.snapshot(1).messages
    assert repo.import_legacy(source) == 2
    assert repo.import_legacy(source) == 0
    assert len(repo.snapshot(1).messages) == 2
    assert source.read_bytes() == before
