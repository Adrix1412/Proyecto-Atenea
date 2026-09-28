"""Short database transactions; never keep a row lock while waiting for the LLM."""

from typing import cast
from uuid import UUID

from django.db import DatabaseError, transaction
from django.db.models import F, Max

from alicia_core.domain import Message, Role, Snapshot, validate_text
from alicia_core.errors import ConversationConflict, StorageError

from .models import Conversation, LegacyImport, MessageRecord


class DjangoMemory:
    def __init__(self, conversation_id: UUID, owner_id: int) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id

    def snapshot(self, max_turns: int = 12) -> Snapshot:
        if not 1 <= max_turns <= 50:
            raise ValueError("max_turns fuera de rango.")
        try:
            with transaction.atomic():
                c = Conversation.objects.select_for_update().get(
                    pk=self.conversation_id, owner_id=self.owner_id
                )
                rows = list(
                    MessageRecord.objects.filter(conversation=c).order_by("-position")[: max_turns * 2]
                )
                return Snapshot(
                    c.revision, tuple(Message(cast(Role, r.role), r.content) for r in reversed(rows))
                )
        except (DatabaseError, Conversation.DoesNotExist) as exc:
            raise StorageError("Conversación no disponible.") from exc

    def append_turn(self, user: str, assistant: str, expected_revision: int) -> None:
        validate_text(user)
        validate_text(assistant)
        try:
            with transaction.atomic():
                changed = Conversation.objects.filter(
                    pk=self.conversation_id, owner_id=self.owner_id, revision=expected_revision
                ).update(revision=F("revision") + 1)
                if changed != 1:
                    raise ConversationConflict("La conversación cambió; vuelva a enviar su mensaje.")
                maximum = MessageRecord.objects.filter(conversation_id=self.conversation_id).aggregate(
                    value=Max("position")
                )["value"]
                start = (maximum or 0) + 1
                MessageRecord.objects.bulk_create(
                    [
                        MessageRecord(
                            conversation_id=self.conversation_id, position=start, role="user", content=user
                        ),
                        MessageRecord(
                            conversation_id=self.conversation_id,
                            position=start + 1,
                            role="assistant",
                            content=assistant,
                        ),
                    ]
                )
        except DatabaseError as exc:
            raise StorageError("No se pudo guardar la conversación.") from exc

    def clear(self) -> None:
        try:
            with transaction.atomic():
                changed = Conversation.objects.filter(pk=self.conversation_id, owner_id=self.owner_id).update(
                    revision=F("revision") + 1
                )
                if changed != 1:
                    raise StorageError("Conversación no disponible.")
                MessageRecord.objects.filter(conversation_id=self.conversation_id).delete()
                LegacyImport.objects.filter(conversation_id=self.conversation_id).delete()
        except DatabaseError as exc:
            raise StorageError("No se pudo eliminar la memoria.") from exc
