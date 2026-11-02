"""Run `manage.py check --deploy` with production-like, throwaway settings.

Used by the Jenkinsfile "Security checks" stage. A random secret key is
generated for this process only; it is never printed or stored.
Exit code is non-zero if Django reports any ERROR-level deployment issue.
"""

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    os.environ.update(
        {
            "DJANGO_SETTINGS_MODULE": "codeguard.settings",
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "ci.invalid",
            "DJANGO_HSTS_SECONDS": "31536000",
            "DJANGO_SECURE_SSL_REDIRECT": "true",
            "DJANGO_SECURE_COOKIES": "true",
        }
    )
    sys.path.insert(0, str(ROOT))
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "check", "--deploy", "--fail-level", "ERROR"])


if __name__ == "__main__":
    main()
