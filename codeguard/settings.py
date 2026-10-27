"""Django settings for CodeGuard.

Environment-specific values are read from environment variables (optionally
loaded from a local ``.env`` file). See ``.env.example`` for the full list.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Development-only fallback; never used when DEBUG is off.
        SECRET_KEY = "django-insecure-codeguard-local-development-only"  # noqa: S105
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false. Copy .env.example to .env for local development."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "audit",
    "threats",
    "simulation",
    "remediation",
    "core",
]

MIDDLEWARE = [
    "core.observability.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "codeguard.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.role",
            ],
        },
    },
]

WSGI_APPLICATION = "codeguard.wsgi.application"

# SQLite, tuned for a small multi-worker deployment (decision and limits:
# docs/architecture.md, "Database: SQLite now, PostgreSQL when"):
# - WAL lets readers continue while one writer commits;
# - IMMEDIATE takes the write lock when a transaction starts, so two writers
#   queue (up to "timeout" seconds) instead of failing with "database is locked"
#   halfway through;
# - synchronous=NORMAL is the recommended durability level for WAL;
# - foreign keys are enforced (Django also enables this by default).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DJANGO_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:landing"

# Role given to self-registered users. Only "analyst" or "viewer" are accepted;
# administrators are promoted by an existing administrator.
CODEGUARD_DEFAULT_ROLE = os.environ.get("CODEGUARD_DEFAULT_ROLE", "analyst")
if CODEGUARD_DEFAULT_ROLE not in {"analyst", "viewer"}:
    raise ImproperlyConfigured("CODEGUARD_DEFAULT_ROLE must be 'analyst' or 'viewer'.")

# Who may create an account. The deployment is the tenancy boundary (one
# organization per instance; see docs/engineering-assessment.md, H2), so public
# deployments should use "domain" or "closed".
#   open   - anyone can register (local development, classroom demos)
#   domain - only email addresses in CODEGUARD_REGISTRATION_DOMAINS
#   closed - no self-registration; administrators create accounts
CODEGUARD_REGISTRATION = os.environ.get("CODEGUARD_REGISTRATION", "open").strip().lower()
CODEGUARD_REGISTRATION_DOMAINS = [d.lower() for d in env_list("CODEGUARD_REGISTRATION_DOMAINS")]
if CODEGUARD_REGISTRATION not in {"open", "domain", "closed"}:
    raise ImproperlyConfigured("CODEGUARD_REGISTRATION must be 'open', 'domain' or 'closed'.")
if CODEGUARD_REGISTRATION == "domain" and not CODEGUARD_REGISTRATION_DOMAINS:
    raise ImproperlyConfigured("CODEGUARD_REGISTRATION=domain needs CODEGUARD_REGISTRATION_DOMAINS.")

# --- Sign-in throttling (accounts/throttling.py) ----------------------------------
CODEGUARD_LOGIN_MAX_FAILURES = int(os.environ.get("CODEGUARD_LOGIN_MAX_FAILURES", "5"))
CODEGUARD_LOGIN_IP_MAX_FAILURES = int(os.environ.get("CODEGUARD_LOGIN_IP_MAX_FAILURES", "20"))
CODEGUARD_LOGIN_LOCKOUT_MINUTES = int(os.environ.get("CODEGUARD_LOGIN_LOCKOUT_MINUTES", "15"))

# --- Email (password reset). Console backend prints emails locally. -------------
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "codeguard@localhost")
# SMTP, used when DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend.
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10

# --- Session and cookie security ------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Production hardening: enabled automatically when DEBUG is off. HTTPS is
# required in that mode (see README "Deployment notes").
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0" if DEBUG else "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = False
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Load balancer / monitoring probes may use plain HTTP inside the network.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

# Logs go to stdout/stderr for the process manager or container runtime to
# collect. Each line carries the request ID (core/observability.py).
CODEGUARD_LOG_FORMAT = os.environ.get("CODEGUARD_LOG_FORMAT", "text").strip().lower()
if CODEGUARD_LOG_FORMAT not in {"text", "json"}:
    raise ImproperlyConfigured("CODEGUARD_LOG_FORMAT must be 'text' or 'json'.")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "core.observability.RequestIdFilter"}},
    "formatters": {
        "text": {"format": "{levelname} {asctime} {name} [{request_id}]: {message}", "style": "{"},
        "json": {"()": "core.observability.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": CODEGUARD_LOG_FORMAT,
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "codeguard": {
            "handlers": ["console"],
            "level": os.environ.get("CODEGUARD_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
