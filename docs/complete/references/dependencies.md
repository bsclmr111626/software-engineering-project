# Reference: dependencies

All Python versions are pinned with `==`. Installed versions in `.venv` were spot-checked on
2026-11-10 (`Django 5.2.18`, `matplotlib 3.11.2`, Python `3.12.10`).

## Runtime (`requirements.txt`)

| Package | Version | Why CodeGuard needs it | Used in |
|---|---|---|---|
| Django | 5.2.18 | Web framework: ORM, migrations, templates, auth, sessions, CSRF, admin | everywhere |
| matplotlib | 3.11.2 | Server-side PNG charts (Agg backend, object-oriented API) | `simulation/charts.py` |
| python-dotenv | 1.2.4 | Loads `.env` into the environment before settings are read | `codeguard/settings.py` (`load_dotenv`) |
| asgiref | 3.13.0 | Django dependency (sync/async adapters) | transitive |
| sqlparse | 0.6.0 | Django dependency (SQL formatting for `sqlmigrate` etc.) | transitive |
| tzdata | 2026.5 | Time-zone database, needed on Windows for `USE_TZ` | transitive |
| numpy | 2.5.4 | Matplotlib dependency | transitive |
| pillow | 13.0.0 | Matplotlib image backend | transitive |
| contourpy, cycler, fonttools, kiwisolver, packaging, pyparsing, python-dateutil, six | see file | Matplotlib dependencies | transitive |

There is no WSGI server in the requirements. `docs/deployment.md` recommends installing
`gunicorn` (Linux) or `waitress` (Windows) separately.

## Development and CI (`requirements-dev.txt`, includes `requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| pytest | 9.1.1 | Test runner (`pytest.ini`) |
| pytest-django | 4.14.0 | Django integration: `db`, `client` fixtures, temporary test database |
| pytest-cov | 7.1.0 | `--cov` option |
| coverage | 7.17.0 | Coverage measurement and the `--fail-under=85` gate |
| ruff | 0.17.2 | Lint (`E F W I B UP DJ S` rule sets) and formatter |
| pip-audit | 2.10.1 | Known-vulnerability scan of `requirements.txt` (`scripts/ci_dependency_audit.py`) |

## Optional verification tools (not needed to run the app)

| Tool | Requirement | Pinned? | Notes |
|---|---|---|---|
| `tools/a11y/*.mjs` | Node.js ≥ 22, Chrome, `axe-core` 4.10.2 (`tools/a11y/package.json`, lockfile committed) | yes | Drives headless Chrome over the DevTools protocol |
| `tools/authz_live.py` | Python `requests` | **no** | `requests` is importable in this `.venv` (2.34.2, pulled in by `pip-audit`), but no requirements file names it |

## Frontend assets (vendored, served from `static/`)

| Asset | Path | Notes |
|---|---|---|
| Bootstrap CSS + bundle JS | `static/vendor/bootstrap/` | Version not recorded in the repository |
| Bootstrap Icons (CSS + fonts) | `static/vendor/bootstrap-icons/` | Version not recorded |
| Google Fonts (Instrument Sans, JetBrains Mono, Newsreader) | loaded from `fonts.googleapis.com` in `templates/base.html` | The only third-party request; allowed by the CSP (`style-src`, `font-src`) |

## Not used

No JavaScript framework or build step, no CDN for JS/CSS, no Celery/Redis, no PostgreSQL driver,
no Docker files, no REST framework or JSON API (apart from `/healthz/` and the personal data
export).
