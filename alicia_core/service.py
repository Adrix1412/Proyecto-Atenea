"""Use case: read a snapshot, generate, atomically persist a complete turn."""

import logging

from .avatar_events import AvatarEventEmitter, AvatarEventType
from .domain import ChatClient, MemoryRepository, validate_text

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(
        self,
        memory: MemoryRepository,
        client: ChatClient,
        max_turns: int = 12,
        avatar_events: AvatarEventEmitter | None = None,
    ) -> None:
        if not 1 <= max_turns <= 50:
            raise ValueError("max_turns debe estar entre 1 y 50.")
        self.memory = memory
        self.client = client
        self.max_turns = max_turns
        self.avatar_events = avatar_events

    def _emit_avatar(self, event_type: AvatarEventType) -> None:
        if self.avatar_events is None:
            return
        try:
            self.avatar_events.emit(event_type)
        except Exception:
            logger.warning("avatar_event_emit_failed")

    def reply(self, text: str) -> str:
        text = validate_text(text)
        self._emit_avatar(AvatarEventType.THINKING)
        try:
            snapshot = self.memory.snapshot(self.max_turns)
            answer = validate_text(self.client.chat(snapshot.messages, text))
            self.memory.append_turn(text, answer, snapshot.revision)
            return answer
        finally:
            self._emit_avatar(AvatarEventType.IDLE)
