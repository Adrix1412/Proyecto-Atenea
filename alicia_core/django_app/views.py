"""Minimal same-origin integration example with session auth and CSRF protection."""

import json
import logging
from uuid import UUID

from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alicia_core.errors import AliciaError, ConversationConflict
from alicia_core.service import ConversationService

from .factory import build_web_client
from .models import Conversation
from .repository import DjangoMemory

logger = logging.getLogger(__name__)


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=16000)


@require_POST
@csrf_protect
def create_conversation(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Autenticación requerida."}, status=401)
    if not cache.add(f"alicia:create:{request.user.pk}", True, timeout=5):
        return JsonResponse({"error": "Espere antes de crear otra conversación."}, status=429)
    try:
        c = Conversation.objects.create(owner=request.user)
        return JsonResponse({"id": str(c.pk)}, status=201)
    except DatabaseError:
        return JsonResponse({"error": "Memoria no disponible."}, status=503)


@require_POST
@csrf_protect
def chat(request: HttpRequest, conversation_id: UUID) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Autenticación requerida."}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Se requiere application/json."}, status=415)
    try:
        if len(request.body) > 65536:
            return JsonResponse({"error": "Solicitud demasiado grande."}, status=413)
        data = ChatInput.model_validate(json.loads(request.body))
    except RequestDataTooBig:
        return JsonResponse({"error": "Solicitud demasiado grande."}, status=413)
    except (ValidationError, ValueError, UnicodeError):
        return JsonResponse({"error": "Mensaje inválido."}, status=400)
    try:
        if not Conversation.objects.filter(pk=conversation_id, owner=request.user).exists():
            return JsonResponse({"error": "Conversación no encontrada."}, status=404)
        if not cache.add(f"alicia:chat:{request.user.pk}", True, timeout=5):
            return JsonResponse({"error": "Espere antes de enviar otro mensaje."}, status=429)
        client = build_web_client()
        try:
            memory = DjangoMemory(conversation_id, request.user.pk)
            reply = ConversationService(memory, client, client.cfg.max_history_turns).reply(data.message)
            return JsonResponse({"reply": reply})
        finally:
            client.close()
    except ConversationConflict:
        return JsonResponse({"error": "La conversación cambió; vuelva a enviar el mensaje."}, status=409)
    except ValueError:
        return JsonResponse({"error": "Mensaje inválido."}, status=400)
    except (AliciaError, DatabaseError) as exc:
        logger.warning("chat_failed type=%s", type(exc).__name__)
        return JsonResponse({"error": "Alicia no está disponible temporalmente."}, status=503)
