"""Use case: read a snapshot, generate, atomically persist a complete turn."""

from .domain import ChatClient, MemoryRepository, validate_text


class ConversationService:
    def __init__(self, memory: MemoryRepository, client: ChatClient, max_turns: int = 12) -> None:
        if not 1 <= max_turns <= 50:
            raise ValueError("max_turns debe estar entre 1 y 50.")
        self.memory = memory
        self.client = client
        self.max_turns = max_turns

    def reply(self, text: str) -> str:
        text = validate_text(text)
        snapshot = self.memory.snapshot(self.max_turns)
        answer = validate_text(self.client.chat(snapshot.messages, text))
        self.memory.append_turn(text, answer, snapshot.revision)
        return answer
