"""Settings used by the automated test suite (pytest.ini points here).

Tests always run against an isolated, temporary SQLite database created by
pytest-django, never against the developer's db.sqlite3.
"""

import os

os.environ.setdefault("DJANGO_DEBUG", "false")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ.setdefault("DJANGO_SECURE_SSL_REDIRECT", "false")

from .settings import *  # noqa: E402,F403

ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CODEGUARD_DEFAULT_ROLE = "analyst"
LOGGING["loggers"]["codeguard"]["level"] = "WARNING"  # noqa: F405
