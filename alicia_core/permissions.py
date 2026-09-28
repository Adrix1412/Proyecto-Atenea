"""One-use local approvals for prevalidated action requests.

Only trusted UI code may issue an approval. This store is process-local and
must not be used as a persistent or distributed permission service.
"""

import hashlib
import json
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import IntEnum
from uuid import UUID


class Risk(IntEnum):
    READ = 0
    REVERSIBLE = 1
    SENSITIVE = 2
    EXTERNAL = 3


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        raise ValueError(f"Identificador inválido: {label}.")


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    actor_id: str
    device_id: str
    capability: str
    arguments: Mapping[str, object]
    risk: Risk

    def __post_init__(self) -> None:
        try:
            UUID(self.request_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("ID de solicitud inválido.") from exc
        for label in ("actor_id", "device_id", "capability"):
            _identifier(getattr(self, label), label)
        if not isinstance(self.risk, Risk) or not isinstance(self.arguments, Mapping):
            raise ValueError("Solicitud inválida.")
        self.fingerprint()

    def fingerprint(self) -> bytes:
        payload = {
            "request_id": self.request_id,
            "actor_id": self.actor_id,
            "device_id": self.device_id,
            "capability": self.capability,
            "arguments": self.arguments,
            "risk": int(self.risk),
        }
        try:
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("Argumentos no serializables.") from exc
        if len(canonical) > 16384:
            raise ValueError("Solicitud demasiado grande.")
        return hashlib.sha256(canonical).digest()


@dataclass(frozen=True)
class _Grant:
    fingerprint: bytes
    expires_at: float


class PermissionEngine:
    """Approvals are bound to exact args, expire, and are consumed atomically."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._grants: dict[bytes, _Grant] = {}
        self._lock = threading.Lock()

    def issue(self, request: ActionRequest, approver_id: str, ttl_sec: int = 60) -> str:
        """Call only after an authenticated user confirms the exact action."""
        if request.risk not in (Risk.REVERSIBLE, Risk.SENSITIVE):
            raise ValueError("La acción no admite esta aprobación.")
        if approver_id != request.actor_id or not 1 <= ttl_sec <= 300:
            raise ValueError("Aprobación inválida.")
        token = secrets.token_urlsafe(32)
        key = hashlib.sha256(token.encode("ascii")).digest()
        grant = _Grant(request.fingerprint(), self._clock() + ttl_sec)
        with self._lock:
            now = self._clock()
            self._grants = {k: v for k, v in self._grants.items() if v.expires_at > now}
            if len(self._grants) >= 1024:
                raise ValueError("Demasiadas aprobaciones pendientes.")
            self._grants[key] = grant
        return token

    def authorize(self, request: ActionRequest, approval_token: str | None = None) -> bool:
        if request.risk is Risk.EXTERNAL:
            return False
        if request.risk is Risk.READ:
            return True
        if not isinstance(approval_token, str) or not approval_token or len(approval_token) > 256:
            return False
        key = hashlib.sha256(approval_token.encode("utf-8")).digest()
        with self._lock:
            grant = self._grants.get(key)
            if grant is None or grant.expires_at <= self._clock():
                self._grants.pop(key, None)
                return False
            if not secrets.compare_digest(grant.fingerprint, request.fingerprint()):
                return False
            del self._grants[key]
            return True
