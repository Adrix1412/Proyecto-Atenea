"""SQLite journal for locally executed actions; never stores approval tokens."""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from alicia_core.execution import ExecutionResult, ExecutionStatus
from alicia_core.permissions import ActionRequest


@dataclass(frozen=True)
class RecordedTask:
    fingerprint: bytes
    status: ExecutionStatus
    message: str


class SqliteTaskJournal:
    """Atomic reservation and terminal updates across processes sharing one database."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS atenea_tasks (
                    request_id TEXT PRIMARY KEY,
                    fingerprint BLOB NOT NULL,
                    actor_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            # An orphan may have performed the external effect before the crash.
            db.execute(
                "UPDATE atenea_tasks SET status = ?, message = ?, updated_at = ? WHERE status = ?",
                (ExecutionStatus.UNKNOWN, "Resultado incierto tras reinicio.", time.time(), "RUNNING"),
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    def get(self, request_id: str) -> RecordedTask | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT fingerprint, status, message FROM atenea_tasks WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return RecordedTask(row[0], ExecutionStatus(row[1]), row[2])

    def reserve(self, request: ActionRequest) -> bool:
        """Return False on duplicate; fail closed on database errors."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now = time.time()
                cursor = db.execute(
                    """INSERT OR IGNORE INTO atenea_tasks
                    (request_id, fingerprint, actor_id, device_id, capability, status, message, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request.request_id,
                        request.fingerprint(),
                        request.actor_id,
                        request.device_id,
                        request.capability,
                        "RUNNING",
                        "Ejecución en curso.",
                        now,
                        now,
                    ),
                )
                db.execute("COMMIT")
                return cursor.rowcount == 1
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def finish(self, request_id: str, result: ExecutionResult) -> None:
        if result.status not in (ExecutionStatus.SUCCEEDED, ExecutionStatus.UNKNOWN):
            raise ValueError("Estado final inválido.")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "UPDATE atenea_tasks SET status = ?, message = ?, updated_at = ? "
                    "WHERE request_id = ? AND status = ?",
                    (result.status, result.message[:6000], time.time(), request_id, "RUNNING"),
                )
                if row.rowcount != 1:
                    raise ValueError("Transición inválida.")
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
