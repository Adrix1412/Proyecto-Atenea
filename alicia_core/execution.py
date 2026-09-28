"""Authorized executor with optional durable task journal."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .permissions import ActionRequest, PermissionEngine

logger = logging.getLogger(__name__)


class ExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    message: str


class TaskJournal(Protocol):
    def get(self, request_id: str) -> object: ...

    def reserve(self, request: ActionRequest) -> bool: ...

    def finish(self, request_id: str, result: ExecutionResult) -> None: ...


class TaskExecutor:
    def __init__(self, journal: TaskJournal | None = None) -> None:
        self.journal = journal

    def run(
        self,
        request: ActionRequest,
        policy: PermissionEngine,
        operation: Callable[[], str],
        approval_token: str | None = None,
    ) -> ExecutionResult:
        try:
            if not policy.authorize(request, approval_token):
                return ExecutionResult(ExecutionStatus.DENIED, "Acción denegada: falta aprobación válida.")
        except Exception as exc:
            logger.warning("authorization_failed type=%s", type(exc).__name__)
            return ExecutionResult(ExecutionStatus.DENIED, "Acción denegada: autorización no disponible.")
        if self.journal is not None:
            try:
                if not self.journal.reserve(request):
                    return ExecutionResult(
                        ExecutionStatus.UNKNOWN,
                        "Solicitud ya registrada: consulte su estado antes de actuar.",
                    )
            except Exception as exc:
                logger.warning("task_reservation_failed type=%s", type(exc).__name__)
                return ExecutionResult(ExecutionStatus.DENIED, "No se pudo registrar la tarea.")
        try:
            result = operation()
            if not isinstance(result, str):
                raise ValueError("Resultado inválido.")
            outcome = ExecutionResult(ExecutionStatus.SUCCEEDED, result[:6000])
        except Exception as exc:
            logger.warning("execution_unknown type=%s", type(exc).__name__)
            outcome = ExecutionResult(
                ExecutionStatus.UNKNOWN,
                "Resultado incierto: consulte el estado antes de volver a ejecutar la acción.",
            )
        if self.journal is not None:
            try:
                self.journal.finish(request.request_id, outcome)
            except Exception as exc:
                logger.warning("task_finish_failed type=%s", type(exc).__name__)
                return ExecutionResult(ExecutionStatus.UNKNOWN, "Estado no guardado: consulte la tarea.")
        return outcome
