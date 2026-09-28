"""Desktop transitional storage. New tables never overwrite legacy exchanges."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from alicia_core.domain import Message, Role, Snapshot, validate_text
from alicia_core.errors import ConversationConflict, StorageError
from alicia_core.legacy import read_legacy


class SQLiteMemory:
    def __init__(self, db_path: Path, conversation: str = "desktop") -> None:
        if not conversation or len(conversation) > 100:
            raise ValueError("Conversación inválida.")
        self.db_path = db_path
        self.conversation = conversation
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, timestamp REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS legacy_imports (conversation_id TEXT PRIMARY KEY, digest TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS message_conversation ON messages(conversation_id, id);
            """)
            c.execute("INSERT OR IGNORE INTO conversations(id) VALUES (?)", (conversation,))
        try:
            db_path.chmod(0o600)
        except OSError as exc:
            raise StorageError("No se pudieron proteger los permisos de la memoria.") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            c = sqlite3.connect(self.db_path, timeout=10)
            try:
                c.execute("PRAGMA foreign_keys=ON")
                with c:
                    yield c
            finally:
                c.close()
        except sqlite3.Error as exc:
            raise StorageError("No se pudo acceder a la memoria SQLite.") from exc

    def snapshot(self, max_turns: int = 12) -> Snapshot:
        if not 1 <= max_turns <= 50:
            raise ValueError("max_turns fuera de rango.")
        with self._connect() as c:
            c.execute("BEGIN")
            revision = c.execute(
                "SELECT revision FROM conversations WHERE id=?", (self.conversation,)
            ).fetchone()[0]
            rows = c.execute(
                "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                (self.conversation, max_turns * 2),
            ).fetchall()
        return Snapshot(revision, tuple(Message(cast(Role, r), t) for r, t in reversed(rows)))

    def append_turn(self, user: str, assistant: str, expected_revision: int) -> None:
        validate_text(user)
        validate_text(assistant)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            changed = c.execute(
                "UPDATE conversations SET revision=revision+1 WHERE id=? AND revision=?",
                (self.conversation, expected_revision),
            ).rowcount
            if changed != 1:
                raise ConversationConflict("La conversación cambió; vuelva a enviar su mensaje.")
            c.executemany(
                "INSERT INTO messages(conversation_id,role,content,timestamp) VALUES (?,?,?,?)",
                [
                    (self.conversation, role, content, time.time())
                    for role, content in (("user", user), ("assistant", assistant))
                ],
            )

    def clear(self) -> None:
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM messages WHERE conversation_id=?", (self.conversation,))
            c.execute("DELETE FROM legacy_imports WHERE conversation_id=?", (self.conversation,))
            c.execute("UPDATE conversations SET revision=revision+1 WHERE id=?", (self.conversation,))

    def import_legacy(self, source: Path, dry_run: bool = False) -> int:
        """Import into an empty conversation, preserving roles, order and timestamps."""
        if source.resolve() == self.db_path.resolve():
            raise StorageError("Use un destino distinto para conservar intacta la base original.")
        digest, rows = read_legacy(source)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            previous = c.execute(
                "SELECT digest FROM legacy_imports WHERE conversation_id=?", (self.conversation,)
            ).fetchone()
            if previous and previous[0] == digest:
                return 0
            if c.execute(
                "SELECT 1 FROM messages WHERE conversation_id=? LIMIT 1", (self.conversation,)
            ).fetchone():
                raise StorageError("La conversación de destino debe estar vacía.")
            if dry_run:
                return len(rows)
            c.executemany(
                "INSERT INTO messages(conversation_id,role,content,timestamp) VALUES (?,?,?,?)",
                [
                    (self.conversation, r.message.role, r.message.content, r.timestamp.timestamp())
                    for r in rows
                ],
            )
            c.execute("INSERT INTO legacy_imports VALUES (?,?)", (self.conversation, digest))
            c.execute("UPDATE conversations SET revision=revision+1 WHERE id=?", (self.conversation,))
        return len(rows)
