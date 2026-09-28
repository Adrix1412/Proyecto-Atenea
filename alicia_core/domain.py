"""Contracts shared by desktop, tests and Django without framework imports."""

from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["user", "assistant"]
MAX_TEXT = 16000


def validate_text(value: str, maximum: int = MAX_TEXT) -> str:
    """Validate before contacting a provider or storing a message."""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"El texto debe contener entre 1 y {maximum} caracteres.")
    if "\x00" in value:
        raise ValueError("El texto contiene un carácter no permitido.")
    return value.strip()


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError("Rol no permitido.")
        validate_text(self.content)


@dataclass(frozen=True)
class Snapshot:
    revision: int
    messages: tuple[Message, ...]


class MemoryRepository(Protocol):
    """Each instance is bound to a single authorized conversation."""

    def snapshot(self, max_turns: int) -> Snapshot: ...
    def append_turn(self, user: str, assistant: str, expected_revision: int) -> None: ...
    def clear(self) -> None: ...


class ChatClient(Protocol):
    def chat(self, history: tuple[Message, ...], user_message: str) -> str: ...
    def close(self) -> None: ...
