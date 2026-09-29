"""Platform-neutral avatar state events for desktop and mobile renderers."""

import logging
import re
import threading
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .config import StrictModel

logger = logging.getLogger(__name__)


class AvatarEventType(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TALKING = "talking"
    WALK_TO = "walk_to"
    WAVE = "wave"
    SLEEP = "sleep"
    EXPRESSION = "expression"
    HIDE = "hide"


class AvatarPosition(StrictModel):
    """A normalized position, portable across screens and mobile viewports."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class AvatarEvent(StrictModel):
    """Versioned intent, never a renderer command or an arbitrary animation path."""

    version: int = Field(default=1, frozen=True)
    event_id: UUID = Field(default_factory=uuid4)
    event_type: AvatarEventType
    position: AvatarPosition | None = None
    expression: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def valid_payload(self) -> "AvatarEvent":
        if self.version != 1:
            raise ValueError("Versión de evento de avatar no admitida.")
        if self.event_type is AvatarEventType.WALK_TO:
            if self.position is None or self.expression is not None:
                raise ValueError("walk_to requiere solo una posición.")
        elif self.event_type is AvatarEventType.EXPRESSION:
            if (
                self.position is not None
                or not self.expression
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.expression)
            ):
                raise ValueError("expression requiere un identificador seguro.")
        elif self.position is not None or self.expression is not None:
            raise ValueError("El evento de avatar no admite datos adicionales.")
        return self


class AvatarEventEnvelope(StrictModel):
    sequence: int = Field(ge=1)
    event: AvatarEvent


class AvatarEventEmitter(Protocol):
    def emit(
        self,
        event_type: AvatarEventType,
        *,
        position: AvatarPosition | None = None,
        expression: str | None = None,
    ) -> AvatarEventEnvelope: ...


AvatarSubscriber = Callable[[AvatarEventEnvelope], None]


class AvatarEventBus:
    """In-process event stream. Renderer failures must never stop conversations."""

    def __init__(self, history_limit: int = 128) -> None:
        if not 1 <= history_limit <= 1024:
            raise ValueError("El historial de avatar debe estar entre 1 y 1024.")
        self._history: deque[AvatarEventEnvelope] = deque(maxlen=history_limit)
        self._subscribers: list[AvatarSubscriber] = []
        self._sequence = 0
        self._lock = threading.RLock()

    def emit(
        self,
        event_type: AvatarEventType,
        *,
        position: AvatarPosition | None = None,
        expression: str | None = None,
    ) -> AvatarEventEnvelope:
        event = AvatarEvent(event_type=event_type, position=position, expression=expression)
        with self._lock:
            self._sequence += 1
            envelope = AvatarEventEnvelope(sequence=self._sequence, event=event)
            self._history.append(envelope)
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(envelope)
            except Exception:
                logger.warning("avatar_subscriber_failed")
        return envelope

    def subscribe(self, subscriber: AvatarSubscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    def events_after(self, sequence: int = 0) -> tuple[AvatarEventEnvelope, ...]:
        if sequence < 0:
            raise ValueError("La secuencia no puede ser negativa.")
        with self._lock:
            return tuple(event for event in self._history if event.sequence > sequence)
