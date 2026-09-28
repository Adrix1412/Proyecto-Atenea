"""Durable task journal keeps effects from being replayed after crashes."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alicia_core.adapters.sqlite_tasks import SqliteTaskJournal
from alicia_core.execution import ExecutionStatus, TaskExecutor
from alicia_core.permissions import ActionRequest, PermissionEngine, Risk


def action() -> ActionRequest:
    return ActionRequest(str(uuid4()), "owner", "pc", "open_app", {"app": "editor"}, Risk.READ)


def test_recovery_blocks_replay_after_crash(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "tasks.db"
    task = action()
    journal = SqliteTaskJournal(path)
    assert journal.reserve(task)
    assert journal.get(task.request_id) is not None
    recovered = SqliteTaskJournal(path)
    assert recovered.get(task.request_id).status is ExecutionStatus.UNKNOWN
    count: list[int] = []
    outcome = TaskExecutor(recovered).run(task, PermissionEngine(), lambda: count.append(1) or "ok")
    assert outcome.status is ExecutionStatus.UNKNOWN
    assert not count


def test_success_and_failure_are_persisted_and_replay_is_blocked(tmp_path: object) -> None:
    from pathlib import Path

    journal = SqliteTaskJournal(Path(str(tmp_path)) / "tasks.db")
    calls: list[str] = []
    task = action()
    executor = TaskExecutor(journal)
    success = executor.run(task, PermissionEngine(), lambda: calls.append("ok") or "listo")
    assert success.status is ExecutionStatus.SUCCEEDED
    assert journal.get(task.request_id).message == "listo"
    assert (
        executor.run(task, PermissionEngine(), lambda: calls.append("duplicate") or "again").status
        is ExecutionStatus.UNKNOWN
    )
    failed = action()

    def crash() -> str:
        calls.append("failed")
        raise OSError("private detail")

    assert executor.run(failed, PermissionEngine(), crash).status is ExecutionStatus.UNKNOWN
    assert journal.get(failed.request_id).status is ExecutionStatus.UNKNOWN
    assert calls == ["ok", "failed"]


def test_concurrent_reservation_single_winner(tmp_path: object) -> None:
    from pathlib import Path

    journal = SqliteTaskJournal(Path(str(tmp_path)) / "tasks.db")
    task = action()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: journal.reserve(task), range(16)))
    assert outcomes.count(True) == 1


def test_database_failure_prevents_execution(tmp_path: object) -> None:
    from pathlib import Path

    journal = SqliteTaskJournal(Path(str(tmp_path)) / "tasks.db")
    Path(journal.path).unlink()
    called: list[int] = []
    outcome = TaskExecutor(journal).run(action(), PermissionEngine(), lambda: called.append(1) or "ok")
    assert outcome.status is ExecutionStatus.DENIED
    assert called == []
