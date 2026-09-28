"""Import the old desktop DB into the configured Django DB without changing the source."""

from argparse import ArgumentParser
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from alicia_core.django_app.models import Conversation, LegacyImport, MessageRecord
from alicia_core.errors import StorageError
from alicia_core.legacy import read_legacy


class Command(BaseCommand):
    help = "Importar exchanges de SQLite a una conversación vacía; repetir el mismo archivo no duplica."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=Path)
        parser.add_argument("--conversation", required=True, type=UUID)
        parser.add_argument("--owner", required=True, type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> str:
        source = options["source"]
        if not isinstance(source, Path):
            raise CommandError("Ruta inválida.")
        conversation_id = options["conversation"]
        owner_id = options["owner"]
        if not isinstance(conversation_id, UUID) or not isinstance(owner_id, int):
            raise CommandError("Conversación o propietario inválido.")
        try:
            digest, rows = read_legacy(source)
            with transaction.atomic():
                c = Conversation.objects.select_for_update().get(pk=conversation_id, owner_id=owner_id)
                if LegacyImport.objects.filter(conversation=c, source_digest=digest).exists():
                    return "Este historial ya fue importado; 0 duplicados."
                if MessageRecord.objects.filter(conversation=c).exists():
                    raise CommandError("El destino debe estar vacío; cree otra conversación para importar.")
                if options["dry_run"]:
                    return f"Validación correcta: {len(rows)} mensajes; no se modificó la base."
                MessageRecord.objects.bulk_create(
                    [
                        MessageRecord(
                            conversation=c,
                            position=i,
                            role=r.message.role,
                            content=r.message.content,
                            created_at=r.timestamp,
                        )
                        for i, r in enumerate(rows, start=1)
                    ],
                    batch_size=500,
                )
                LegacyImport.objects.create(conversation=c, source_digest=digest, rows=len(rows))
                c.revision += 1
                c.save(update_fields=["revision"])
                return f"Importados {len(rows)} mensajes. Fuente intacta."
        except (StorageError, DatabaseError, Conversation.DoesNotExist) as exc:
            raise CommandError("Importación cancelada; revise fuente, propietario y conversación.") from exc
