"""Read-only bounded import of the original exchanges SQLite schema."""

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alicia_core.domain import Message, Role
from alicia_core.errors import StorageError


@dataclass(frozen=True)
class LegacyRow:
    message: Message
    timestamp: datetime


def read_legacy(path: Path) -> tuple[str, tuple[LegacyRow, ...]]:
    if not path.is_file() or path.stat().st_size > 100_000_000:
        raise StorageError("Use una copia SQLite existente de hasta 100 MB.")
    try:
        # Hash logical contents in one read transaction, so WAL data is included.
        digest = hashlib.sha256()
        rows: list[LegacyRow] = []
        c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            c.execute("PRAGMA query_only=ON")
            c.execute("BEGIN")
            for identifier, timestamp, role, content in c.execute(
                "SELECT id,timestamp,role,content FROM exchanges ORDER BY id LIMIT 100001"
            ):
                if (
                    len(rows) == 100000
                    or not isinstance(timestamp, (float, int))
                    or not math.isfinite(timestamp)
                ):
                    raise ValueError("Historial fuera de límites.")
                message = Message(cast(Role, role), content)
                row = LegacyRow(message, datetime.fromtimestamp(timestamp, UTC))
                rows.append(row)
                digest.update(json.dumps([identifier, timestamp, role, content], ensure_ascii=False).encode())
                digest.update(b"\n")
        finally:
            c.close()
        return digest.hexdigest(), tuple(rows)
    except (OSError, sqlite3.Error, ValueError, OverflowError, TypeError) as exc:
        raise StorageError("El historial legado no es válido; no se importó ningún registro.") from exc
