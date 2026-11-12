# Development and deployment

The README's **Quick start** (tested by the project) and `docs/deployment.md` (single-server
production guide) already cover installation and operations. This document does not repeat
them; it explains how the pieces fit, records the Windows specifics of this machine, describes
Git/GitHub and CI status, and lists hosting options honestly.

## 1. Local development

### 1.1 Prerequisites

Python **3.12 or newer** (`pyproject.toml`: `requires-python = ">=3.12"`; verified only on
3.12.10), Git, and optionally Node 22+ and Chrome for `tools/a11y/`.

On this development machine Python is installed per user and is **not on `PATH`**: use
`.venv\Scripts\python.exe` for every command. Git is at `C:\Program Files\Git\cmd\git.exe`.

### 1.2 Set-up sequence and why each step exists

| Step | Command | Why |
|---|---|---|
| 1 | `python -m venv .venv` | Isolates the pinned dependencies |
| 2 | `pip install -r requirements-dev.txt` (or `requirements.txt` to only run the app) | Installs Django, Matplotlib, python-dotenv (+ test/lint tools) |
| 3 | copy `.env.example` to `.env` | Sets `DJANGO_DEBUG=true` and a placeholder secret; without a secret and with DEBUG off, settings raise `ImproperlyConfigured` |
| 4 | `python manage.py migrate` | Creates the 23 tables |
| 5 | `python manage.py seed_codeguard --demo-users` | Stages, controls, six scenarios, and three development-only accounts |
| 6 | `python manage.py runserver` | Development server on `http://127.0.0.1:8000/` |

`python manage.py createsuperuser` creates a real administrator (superusers are always treated
as admin by `get_role`).

### 1.3 Day-to-day loop

1. Change code; for models, follow the workflow in `DATABASE_AND_MIGRATIONS.md` §2.9.
2. For UI work, follow `DESIGN.md` and use the CSS variables (`CLAUDE.md` says the same);
   `core/tests/test_design.py` fails on colour literals.
3. Run `pytest` and `ruff check . && ruff format --check .`, or `scripts\ci_local.ps1` for every
   gate.
4. Templates are cached when the server runs with `--noreload` (`tools/a11y/README.md`).

### 1.4 Management commands

| Command | App | Purpose |
|---|---|---|
| `seed_codeguard [--reset-scenarios] [--demo-users]` | threats | Idempotent reference data |
| `backup_db [--output DIR] [--keep N]` | core | Online, integrity-checked SQLite backup |
| `purge_audit_events [--days N] [--dry-run]` | audit | Retention; refuses < 30 days |
| Django built-ins | — | `migrate`, `makemigrations`, `createsuperuser`, `check --deploy`, `collectstatic`, `showmigrations`, `sqlmigrate` |

## 2. Configuration model

All environment-specific values come from environment variables, optionally from `.env`
(full list: [environment variables](references/environment-variables.md)). The single switch
`DJANGO_DEBUG=false` changes the defaults of `SECURE_SSL_REDIRECT`, secure cookies and HSTS
(3600 s), requires a real secret key, and empties `ALLOWED_HOSTS` unless set. Settings validate
their own enumerations at import time (`CODEGUARD_DEFAULT_ROLE`, `CODEGUARD_REGISTRATION`,
`CODEGUARD_LOG_FORMAT`), so a typo stops the process at start-up instead of misbehaving.

`codeguard/test_settings.py` is a thin overlay for tests and CI; there is no separate
production settings module.

## 3. Git and GitHub

* Remote: `origin` → `https://github.com/bsclmr111626/software-engineering-project.git`.
* History on `main` (10 commits, 2026-10-27 to 2026-11-10), all authored by
  `bsclmr134322-collab <bsclmr134322@spu.ac.ke>`, from "Add project skeleton and Django settings"
  to "Add quick start guide to README".
* Project contribution rules: `CONTRIBUTING.md`; issue templates in `.github/ISSUE_TEMPLATE/`
  (bug report, feature request); `.github/pull_request_template.md`.
* `.gitattributes` and `.gitignore` are present. **Problem found:** the `.gitignore` rule
  `reports/` (intended for CI output) also matches `templates/reports/`, so
  `templates/reports/list.html` and `document.html` were never committed. Fixed in commit `eef6716`:
  the rule is now `/reports/` and both templates are tracked.
* `CLAUDE.md` is listed in `.gitignore` ("Local assistant instructions (not shared)");
  `DESIGN.md` is tracked.

## 4. Continuous integration

Diagram and stage list: [CI/CD](diagrams/ci-cd.md).

| Pipeline | Defined in | Executed? | Deploys? |
|---|---|---|---|
| Jenkins (declared primary) | `Jenkinsfile` (7 stages, Declarative) | **Never on a Jenkins server.** Commands rehearsed by `scripts/rehearse_jenkinsfile.py` on 2026-10-26 (README: SUCCESS). Groovy parsing, plugins (`junit`, `archiveArtifacts`, `recordCoverage`, `timestamps`), `post` blocks and agents are unverified | no |
| GitHub Actions (supplementary) | `.github/workflows/ci.yml` | **Yes, passing** since run #7 on commit `8ca8b36`, 2026-11-10, 1 min 5 s. Runs #1–#6 failed: missing Reports templates (fixed in `eef6716`), then Ruff formatting Markdown code blocks (fixed in `8ca8b36`) | no |
| Local | `scripts/ci_local.ps1`, `scripts/ci_local.sh` | Can be run any time | no |

The Jenkinsfile's design choices that matter: `disableConcurrentBuilds`, 30-minute timeout, an
isolated CI database under `reports/`, seeding twice to prove idempotency, JUnit XML and
coverage artefacts, and security checks moved into Python scripts so the Groovy sandbox needs no
script approvals (`tests/test_ci_scripts.py::test_jenkinsfile_uses_scripts_and_no_sandbox_restricted_calls`).
The README's "How to run it for real" section gives the steps to install Jenkins (Windows or
Docker) and create the job.

There is **no CD**: no stage builds an artefact for release, pushes an image or deploys.

## 5. Deployment

### 5.1 What exists

`docs/deployment.md` describes one Linux host running a WSGI server behind a TLS-terminating
reverse proxy with SQLite on local disk: the production variable table, a first-deployment
command sequence, a systemd unit and an nginx block (both marked "example, not tested here"),
health checks, backup/restore, retention and upgrades. Its statement of what was verified is
accurate: settings, `check --deploy`, the health check, request IDs, JSON logging and the
backup/retention commands are tested; the proxy and process-manager snippets are not.

Requirements the code imposes on any deployment:

* `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`; `DJANGO_CSRF_TRUSTED_ORIGINS`
  when the origin differs; `DJANGO_BEHIND_PROXY=true` only behind a proxy that overwrites
  `X-Forwarded-Proto`.
* HTTPS, because secure cookies and the HTTPS redirect are on by default.
* Static files: `collectstatic` into `staticfiles/` and serve them from the proxy. CodeGuard does
  **not** include WhiteNoise or any other static-file middleware, so with DEBUG off Django will
  not serve `/static/` itself.
* A WSGI server installed separately (`gunicorn`/`waitress`; not in requirements).
* The two Reports templates, which a deployment from Git includes only from commit `eef6716` on.

### 5.2 Hosting options

| Option | Status |
|---|---|
| PythonAnywhere, free Beginner plan | **Deployed and verified** on 2026-11-12: <https://codeguard.pythonanywhere.com> |
| Own Linux server or VM (the path `docs/deployment.md` §1–9 describes) | not set up, not tested |
| Containers | no `Dockerfile` exists |

### 5.3 The live instance on PythonAnywhere

Why this host: it keeps files on a persistent disk (the SQLite database survives restarts),
runs Django through its own WSGI server, maps `/static/` without WhiteNoise and provides HTTPS
on `codeguard.pythonanywhere.com`, all without a credit card. Hosts with ephemeral disks or
serverless functions (Render free, Koyeb free, Vercel) would lose the SQLite file or need a
hosted database.

| Item | Value |
|---|---|
| Account / plan | `codeguard`, Beginner ($0): 1 web app, 512 MB disk, 100 console CPU-seconds a day |
| Source | `git clone https://github.com/20Jojo/codeguard.git` into `/home/codeguard/codeguard` |
| Python / virtualenv | 3.12, `/home/codeguard/.virtualenvs/codeguard`, `pip install --no-cache-dir -r requirements.txt` |
| Configuration | `.env` in the project folder (mode 600, never committed): `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_BEHIND_PROXY=true`, `CODEGUARD_REGISTRATION=closed`, `CODEGUARD_DEFAULT_ROLE=analyst`, and a secret key generated on the server |
| Database | SQLite at `/home/codeguard/codeguard/db.sqlite3`; `migrate`, then `seed_codeguard` without `--demo-users` |
| WSGI file | `/var/www/codeguard_pythonanywhere_com_wsgi.py`: adds the project to `sys.path`, sets `DJANGO_SETTINGS_MODULE`, exposes `get_wsgi_application()`; settings load `.env` themselves |
| Static files | Web tab mapping `/static/` → `/home/codeguard/codeguard/staticfiles` (135 files from `collectstatic`) |
| HTTPS | Web tab "Force HTTPS" on; Django's own redirect, secure cookies and HSTS (3600 s) also active |

**Checked on 2026-11-12**: `check --deploy` on the server gave 0 errors and two warnings
(`security.W005`, `security.W021`); `http://` redirects (302) to `https://`; the home page
returns 200 with the full Content-Security-Policy, HSTS, `X-Frame-Options: DENY`, `nosniff`,
Referrer, Permissions and Cross-Origin-Opener policies and an `X-Request-ID`; `/healthz/`
returns `{"status": "ok", "database": "ok"}`; the stylesheets load; `/accounts/register/`
returns 403 (registration closed); unknown paths get CodeGuard's 404 page. Signing in and
running a simulation were confirmed by the owner. **Not checked**: which address
`REMOTE_ADDR` holds behind PythonAnywhere's proxy (see [SECURITY.md](SECURITY.md) §1),
password-reset email (the console backend is still configured, so no mail is sent), and
behaviour under load.

**Upkeep**: on the Web tab, click "Run until 3 months from today" before the free web app
expires; to release a change, push to `20Jojo/codeguard`, then in a Bash console
`cd ~/codeguard`, `git pull`, `python manage.py migrate`, `python manage.py collectstatic
--noinput`, and click Reload. Full steps: `docs/deployment.md` §10.

## 6. Operations

| Need | Mechanism |
|---|---|
| Liveness/readiness | `GET /healthz/` → `200 {"status":"ok","database":"ok"}` or `503` |
| Correlating logs | `X-Request-ID` header and `[request_id]` in every log line; `CODEGUARD_LOG_FORMAT=json` for collectors |
| What to alert on | per `docs/deployment.md` §6: health failures, ERROR lines, bursts of `login_throttled`, `simulation_failed` |
| Backups | `backup_db` nightly; copy off-host; restore drill periodically |
| Retention | `purge_audit_events --days 365` |
| Upgrades | backup → deploy → `check --deploy` → `migrate` → `seed_codeguard` → `collectstatic` → restart |

## 7. Troubleshooting

| Symptom | Cause in the code | Fix |
|---|---|---|
| `ImproperlyConfigured: DJANGO_SECRET_KEY must be set…` | DEBUG false and no key | create `.env` from `.env.example` or set the variable |
| `ImproperlyConfigured: CODEGUARD_REGISTRATION=domain needs…` | domain mode without domains | set `CODEGUARD_REGISTRATION_DOMAINS` |
| `no such table` | migrations not applied | `python manage.py migrate` |
| Empty scenario library / hub | seed not run | `python manage.py seed_codeguard` |
| `TemplateDoesNotExist: reports/list.html` (500 on `/reports/`) | checkout older than `eef6716` (templates were git-ignored) | update to `eef6716` or later |
| Login says "Too many failed sign-in attempts" | throttling (5/user, 20/IP, 15 min) | wait, or adjust the `CODEGUARD_LOGIN_*` variables |
| Signed out with "This session was signed out from another device" | session epoch changed (Settings → Sessions) | sign in again |
| Pages load without styles in production | static files not collected or not served | `collectstatic` and a proxy `location /static/` |
| Redirect loop or "insecure" errors behind a proxy | `X-Forwarded-Proto` not trusted | `DJANGO_BEHIND_PROXY=true` |
| `database is locked` | long write transactions on SQLite | already mitigated (IMMEDIATE + 20 s); otherwise reduce concurrent writers |
| `python` not found on this machine | per-user Python not on PATH | `.venv\Scripts\python.exe …` |
| Charts in the wrong colours | JavaScript disabled or bad `?palette=` | expected fallback to the light palette |
| Demo users refused | `seed_codeguard --demo-users` with DEBUG off | development only by design |
