"""Ephemeral test configuration; never use this module to deploy."""

import os
import secrets

SECRET_KEY = secrets.token_urlsafe(48)
DEBUG = False
USE_TZ = True
ALLOWED_HOSTS = ["testserver"]
ROOT_URLCONF = "alicia_core.django_app.urls"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "alicia_core.django_app",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
if os.environ.get("ALICIA_TEST_POSTGRES") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["PGDATABASE"],
            "USER": os.environ["PGUSER"],
            "PASSWORD": os.environ["PGPASSWORD"],
            "HOST": os.environ["PGHOST"],
            "PORT": os.environ.get("PGPORT", "5432"),
        }
    }
ALICIA_CONFIG_PATH = "config.core.example.yaml"
