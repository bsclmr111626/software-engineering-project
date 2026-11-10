# Reference: environment variables

Read in `codeguard/settings.py` with `os.environ`, after `load_dotenv(BASE_DIR / ".env")`.
`python-dotenv` does not override variables that are already set, so real environment
variables win over `.env`. Booleans go through `env_bool()`: `1`, `true`, `yes`, `on`
(case-insensitive) mean true. Lists go through `env_list()`: comma-separated, blanks dropped.

"In .env.example" says whether the template lists it (commented-out entries count).

## Application settings

| Variable | Default | Effect | Validated | In .env.example |
|---|---|---|---|---|
| `DJANGO_DEBUG` | `False` | Debug mode; also flips the production-hardening defaults below | — | yes |
| `DJANGO_SECRET_KEY` | none | Signing key. If empty: a fixed insecure fallback when DEBUG is true, otherwise `ImproperlyConfigured` at start-up | yes | yes (placeholder) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` when DEBUG, else empty | `ALLOWED_HOSTS` | — | yes |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | `CSRF_TRUSTED_ORIGINS` (scheme included) | — | yes |
| `DJANGO_DB_PATH` | `<BASE_DIR>/db.sqlite3` | SQLite file path | — | yes (commented) |
| `CODEGUARD_DEFAULT_ROLE` | `analyst` | Role of self-registered users | must be `analyst` or `viewer` | yes |
| `CODEGUARD_REGISTRATION` | `open` | `open`, `domain` or `closed` self-registration | yes; `domain` requires the next variable | yes |
| `CODEGUARD_REGISTRATION_DOMAINS` | empty | Allowed email domains for `domain` mode (lower-cased) | — | yes (commented) |
| `CODEGUARD_LOGIN_MAX_FAILURES` | `5` | Failed sign-ins per username in the window before lock | `int()` | yes (commented) |
| `CODEGUARD_LOGIN_IP_MAX_FAILURES` | `20` | Failed sign-ins per client IP in the window | `int()` | yes (commented) |
| `CODEGUARD_LOGIN_LOCKOUT_MINUTES` | `15` | Sliding window length | `int()` | yes (commented) |
| `CODEGUARD_LOG_FORMAT` | `text` | `text` or `json` log lines | yes | yes (commented) |
| `CODEGUARD_LOG_LEVEL` | `INFO` | Level of the `codeguard` logger | — | yes (commented) |

## Email (password reset)

| Variable | Default | In .env.example |
|---|---|---|
| `DJANGO_EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` (prints mail to the console) | yes (commented) |
| `DJANGO_DEFAULT_FROM_EMAIL` | `codeguard@localhost` | yes (commented) |
| `DJANGO_EMAIL_HOST` | `localhost` | yes (commented) |
| `DJANGO_EMAIL_PORT` | `587` | yes (commented) |
| `DJANGO_EMAIL_HOST_USER` | empty | yes (commented) |
| `DJANGO_EMAIL_HOST_PASSWORD` | empty | yes (commented; a secret, never commit a value) |
| `DJANGO_EMAIL_USE_TLS` | `True` | yes (commented) |

## Transport security (defaults depend on DEBUG)

| Variable | Default when DEBUG=false | Default when DEBUG=true | Setting | In .env.example |
|---|---|---|---|---|
| `DJANGO_SECURE_SSL_REDIRECT` | true | false | `SECURE_SSL_REDIRECT` | yes (commented) |
| `DJANGO_SECURE_COOKIES` | true | false | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | yes (commented) |
| `DJANGO_HSTS_SECONDS` | `3600` | `0` | `SECURE_HSTS_SECONDS` | yes (commented) |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | false | false | `SECURE_HSTS_INCLUDE_SUBDOMAINS` | **no** |
| `DJANGO_BEHIND_PROXY` | false | false | when true, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` | yes (commented) |

## Test and CI

| Variable | Where | Value |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `pytest.ini`, `Jenkinsfile`, `.github/workflows/ci.yml`, `scripts/ci_local.*` | `codeguard.test_settings` |
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_SECURE_SSL_REDIRECT` | `codeguard/test_settings.py` (`os.environ.setdefault`) | `false`, a test-only key, `false` |
| `DJANGO_DB_PATH` | `Jenkinsfile` | `${WORKSPACE}/reports/ci-db.sqlite3` (pytest itself still uses a temporary DB) |
| `CORE_COVERAGE_MIN` | `Jenkinsfile` | `85` |
| `PIP_DISABLE_PIP_VERSION_CHECK`, `PYTHONDONTWRITEBYTECODE` | `Jenkinsfile` | `1` |
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY` (random), `DJANGO_ALLOWED_HOSTS=ci.invalid`, `DJANGO_HSTS_SECONDS=31536000`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES` | `scripts/ci_deploy_check.py` (process-local) | production-like values for `check --deploy` |

## Verification tools

| Variable | Tool | Default |
|---|---|---|
| `CODEGUARD_URL` | `tools/authz_live.py`, `tools/a11y/*.mjs` | `http://127.0.0.1:8000` |
| `DJANGO_DB_PATH` | `tools/authz_live.py` (reads the DB to prove it was not changed) | `<repo>/db.sqlite3` |
| `DEMO_PASSWORD` | `tools/authz_live.py` | the documented development demo password |
| `CHROME_PATH` | `tools/a11y/cdp.mjs` | the standard Chrome install path for the OS (`google-chrome` on Linux) |
| `CODEGUARD_ERROR_URL` | `tools/a11y/audit.mjs` | unset; point it at a second server with DEBUG off to audit real error pages |
| `CODEGUARD_THEME` | `tools/a11y` | light; `dark` audits the dark theme |

The local `.env` file was deliberately not opened while writing this documentation.
