"""Run on SQLite locally and PostgreSQL in CI using the same repository contract."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from alicia_core.django_app.models import Conversation, MessageRecord
from alicia_core.django_app.repository import DjangoMemory
from alicia_core.errors import ConversationConflict, StorageError

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(username="owner")


@pytest.fixture
def conversation(owner):
    return Conversation.objects.create(owner=owner)


def test_repository_ownership_atomicity_and_conflict(owner, conversation) -> None:
    repo = DjangoMemory(conversation.pk, owner.pk)
    repo.append_turn("pregunta", "respuesta", 0)
    assert [m.content for m in repo.snapshot(1).messages] == ["pregunta", "respuesta"]
    with pytest.raises(ConversationConflict):
        repo.append_turn("old", "old", 0)
    other = get_user_model().objects.create_user(username="other")
    with pytest.raises(StorageError):
        DjangoMemory(conversation.pk, other.pk).snapshot(1)
    with pytest.raises(ConversationConflict):
        DjangoMemory(conversation.pk, other.pk).append_turn("x", "y", 1)
    with pytest.raises(StorageError):
        DjangoMemory(conversation.pk, other.pk).clear()
    assert MessageRecord.objects.count() == 2
    repo.clear()
    assert not repo.snapshot(1).messages


def make_legacy(path: Path, invalid: bool = False) -> None:
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE exchanges(id INTEGER PRIMARY KEY,timestamp REAL,role TEXT,content TEXT)")
        c.executemany(
            "INSERT INTO exchanges VALUES(?,?,?,?)",
            [
                (1, 1700000000.0, "user", "hola"),
                (2, 1700000001.0, "system" if invalid else "assistant", "respuesta"),
            ],
        )


def test_legacy_import_dry_run_idempotent_and_read_only(tmp_path: Path, owner, conversation) -> None:
    path = tmp_path / "old.db"
    make_legacy(path)
    before = path.read_bytes()
    opts = {"conversation": conversation.pk, "owner": owner.pk}
    call_command("import_alicia_sqlite", path, dry_run=True, **opts)
    assert not MessageRecord.objects.exists()
    call_command("import_alicia_sqlite", path, **opts)
    call_command("import_alicia_sqlite", path, **opts)
    assert MessageRecord.objects.count() == 2
    assert MessageRecord.objects.first().created_at.timestamp() == 1700000000.0
    assert path.read_bytes() == before


def test_bad_import_writes_nothing(tmp_path: Path, owner, conversation) -> None:
    path = tmp_path / "bad.db"
    make_legacy(path, invalid=True)
    with pytest.raises(CommandError):
        call_command("import_alicia_sqlite", path, conversation=conversation.pk, owner=owner.pk)
    assert MessageRecord.objects.count() == 0


def test_api_requires_auth_and_csrf(owner, conversation) -> None:
    url = f"/conversations/{conversation.pk}/messages/"
    assert Client().post(url, data={"message": "hola"}, content_type="application/json").status_code == 401
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    assert client.post(url, data={"message": "hola"}, content_type="application/json").status_code == 403
    assert client.get(url).status_code == 405


def test_api_other_owner_cannot_access_or_call_provider(conversation) -> None:
    other = get_user_model().objects.create_user(username="other")
    client = Client()
    client.force_login(other)
    with patch("alicia_core.django_app.views.build_web_client") as build:
        response = client.post(
            f"/conversations/{conversation.pk}/messages/",
            data={"message": "hola"},
            content_type="application/json",
        )
    assert response.status_code == 404
    build.assert_not_called()


def test_api_validates_payload_before_provider(owner, conversation) -> None:
    client = Client()
    client.force_login(owner)
    with patch("alicia_core.django_app.views.build_web_client") as build:
        response = client.post(
            f"/conversations/{conversation.pk}/messages/",
            data={"message": "hola", "apps": {}},
            content_type="application/json",
        )
    assert response.status_code == 400
    build.assert_not_called()


def test_api_stores_turn_and_rate_limits(owner, conversation) -> None:
    cache.clear()
    client = Client()
    client.force_login(owner)
    with patch("alicia_core.django_app.views.build_web_client") as build:
        build.return_value.cfg.max_history_turns = 12
        build.return_value.chat.return_value = "Hola"
        url = f"/conversations/{conversation.pk}/messages/"
        response = client.post(url, data={"message": "mensaje"}, content_type="application/json")
        second = client.post(url, data={"message": "mensaje"}, content_type="application/json")
    assert response.status_code == 200
    assert second.status_code == 429
    assert MessageRecord.objects.count() == 2
    build.return_value.close.assert_called_once()


def test_api_rejects_large_body(owner, conversation) -> None:
    from django.test import override_settings

    client = Client()
    client.force_login(owner)
    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=65536):
        result = client.post(
            f"/conversations/{conversation.pk}/messages/",
            data={"message": "x" * 70000},
            content_type="application/json",
        )
    assert result.status_code == 413
