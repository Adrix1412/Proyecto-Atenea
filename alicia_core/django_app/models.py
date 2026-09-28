"""Owner-scoped conversations and ordered messages, portable to PostgreSQL."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)


class MessageRecord(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    position = models.PositiveBigIntegerField()
    role = models.CharField(max_length=9, choices=[("user", "User"), ("assistant", "Assistant")])
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "position"], name="alicia_unique_position"),
            models.CheckConstraint(
                condition=models.Q(role__in=["user", "assistant"]), name="alicia_valid_role"
            ),
            models.CheckConstraint(condition=~models.Q(content=""), name="alicia_nonempty_content"),
        ]


class LegacyImport(models.Model):
    """Successful whole-file import marker; clearing memory removes this marker."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    source_digest = models.CharField(max_length=64)
    rows = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "source_digest"], name="alicia_unique_import")
        ]
