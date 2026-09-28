"""Include these routes behind the host project's authentication middleware."""

from django.urls import path

from . import views

app_name = "alicia"
urlpatterns = [
    path("conversations/", views.create_conversation, name="create"),
    path("conversations/<uuid:conversation_id>/messages/", views.chat, name="chat"),
]
