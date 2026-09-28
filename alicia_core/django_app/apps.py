"""Installable Django application; no providers are instantiated at startup."""

from django.apps import AppConfig


class AliciaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alicia_core.django_app"
    label = "alicia"
