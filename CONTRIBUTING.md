# Contributing to CodeGuard

## Lean Software Development in this project

| Principle | How we apply it |
|---|---|
| Eliminate waste | A monolith with no REST API, SPA, Celery or PostgreSQL. Features outside the requirements (PDF export, Monte-Carlo mode) are deferred until someone needs them. |
| Build quality in | Server-side validation, DB constraints, 222 automated tests, accessibility checks, Ruff and a CI gate on every change. The engine is written to be testable first. |
| Defer irreversible decisions | SQLite and settings driven by environment variables keep deployment options open. The engine API (dataclasses) allows a probabilistic mode later without schema changes. |
| Deliver fast in small increments | Seven milestones, each a working, testable vertical slice (see `PLAN.md`). |
| Optimise the whole | One pipeline runs lint, migrations, tests, coverage and security checks, so a single green build means the product works end to end. |
| Learn through feedback | Before/after comparisons and the audit log produce measurable outcomes. CI reports (JUnit, coverage, pip-audit) feed every pull request. |

## Workflow

1. Pick or open an issue (see the suggested backlog below).
2. Create a branch from `main` using the naming convention below.
3. Make small commits with clear messages, for example: `feat(simulation): add reverse-edge explanation`.
4. Run `scripts/ci_local.ps1` (Windows) or `scripts/ci_local.sh` before pushing.
5. Open a pull request using the template. CI must be green, and at least one reviewer must approve.
6. Squash-merge into `main`.

### Branch naming

| Prefix | Use |
|---|---|
| `feature/<issue>-short-name` | New functionality (`feature/12-pdf-export`) |
| `fix/<issue>-short-name` | Bug fixes |
| `docs/<short-name>` | Documentation only |
| `test/<short-name>` | Tests only |
| `chore/<short-name>` | Tooling, dependencies, CI |

### Commit messages

Use Conventional Commits: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.

### Code standards

- Business rules belong in `services.py` or the engine, not in views or templates.
- The engine (`simulation/domain.py`, `engine.py`, `propagation.py`, `risk.py`, `recommendations.py`) must not import Django.
- Every model change needs a migration (`python manage.py makemigrations`), and CI checks for missing ones.
- New behaviour needs tests. Engine changes need hand-calculated expected values.
- Never commit `.env`, databases or secrets.

## Milestones

1. Foundation and authentication
2. Threat library and database
3. Simulation engine and unit tests
4. Dashboard and visualisations
5. Mitigations, history and audit
6. Security hardening, integration tests and CI/CD
7. Documentation and acceptance

## Suggested backlog (future GitHub issues)

| # | Title | Labels | Milestone |
|---|---|---|---|
| 1 | Add login rate limiting (django-axes) | security, enhancement | Hardening |
| 2 | Optional probabilistic mode with a stored random seed | simulation, enhancement | Future |
| 3 | PDF export of reports | reports, enhancement | Future |
| 4 | Admin UI for editing the control catalog (currently via Django admin) | ui | Future |
| 5 | Per-stage impact overrides in custom scenarios | simulation | Future |
| 6 | Organisation/team sharing instead of all-user sharing | auth, enhancement | Future |
| 7 | Accessibility audit with a screen reader | a11y | Hardening |
| 8 | Deployment guide (gunicorn + nginx + HTTPS) | docs, devops | Future |
