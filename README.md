# CodeGuard — Software Supply Chain Risk Simulator

CodeGuard is an **educational** web application that shows how a security compromise can propagate through the software supply chain, from a developer's laptop to production, and how security controls change that outcome. Every score, decision and recommendation is produced by documented, deterministic rules you can inspect.

> CodeGuard is a simulation for teaching and discussion. It never scans, attacks or connects to real systems, its scenarios are hypothetical, and its numbers are illustrative model outputs, **not** a replacement for a professional security assessment.

## Features

- **Five-stage supply chain model**: IDE / Developer Environment → Version Control → CI/CD Pipeline → Software Registry → Production, as a directed graph with forward, bypass and reverse edges.
- **Threat library**: six seeded teaching scenarios plus private custom scenarios (create, edit with versioning, archive, delete, clone), with search, filters and pagination.
- **Deterministic simulation engine**: graph traversal with threshold-based propagation, cycle-safe, fully reproducible.
- **Explainable risk scoring**: inherent vs residual risk per stage and overall, with plain-language reasoning for every stage and edge.
- **Security control catalog**: 14 preventive, detective and recovery controls. Each states the assumption behind its illustrative effectiveness value and what it does not cover.
- **Recommendations**: each one is computed by re-running the model with the control added, so it reports the exact modeled reduction.
- **Before/after comparison**: rerun with different controls and compare runs stage by stage.
- **Remediation plan**: add a recommended control to a private plan, track status, due date and notes, and see it verified when a later run with the control enabled confirms the modeled reduction.
- **Historical reports**: immutable, versioned snapshots; CSV export; optional read-only sharing.
- **Matplotlib charts**: overall risk, risk by stage, propagation outcomes, before/after, and dashboard distribution.
- **Dashboard**: live metrics from the database, with empty states.
- **Roles**: Administrator, Analyst and Viewer, enforced on the server, plus object ownership.
- **Audit log**: append-only (single and bulk changes refused) and sanitised (never stores passwords or tokens), with a retention command.
- **Security hardening**: sign-in throttling, a registration policy (open, allowed email domains, or closed), strict CSP, security headers, CSRF, IDOR protection, secure cookie settings, and friendly error pages.
- **Operations**: `/healthz/` health check, request IDs on every response and log line, optional JSON logs, online verified backups (`backup_db`), and a [deployment guide](docs/deployment.md).
- **Light and dark themes**: paper-like light theme by default, a dark theme that follows the OS setting until you pick one with the sidebar toggle (saved in the browser).
- **Accessibility**: WCAG 2.2 AA automated audit (axe-core) at desktop and phone widths. Since the paper-theme redesign, four colour pairs fail text contrast (see Accessibility below); every other check passes. The app also provides keyboard operation with visible focus, labelled forms whose errors are announced, and text alternatives for the diagram and charts.
- **Tests and CI**: 268 automated tests, 96% coverage, a Jenkins pipeline, GitHub Actions, Ruff, and optional browser-based verification tools.

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS (5.2.18), Django ORM, auth and sessions |
| Database | SQLite |
| Frontend | Django templates, Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 (vendored locally), custom CSS, vanilla JS |
| Charts | Matplotlib 3.11 (Agg backend, rendered in memory) |
| Quality | pytest, pytest-django, pytest-cov / Coverage.py, Ruff, pip-audit |
| CI/CD | Jenkins Declarative Pipeline (`Jenkinsfile`); GitHub Actions as a supplement |

## Architecture summary

```
Browser ──► Django views (accounts, threats, simulation, audit, core)
               │  forms validate input · permissions checked server-side
               ▼
           Service layer (threats/services.py, simulation/services.py, audit/services.py)
               │                                   │
               ▼                                   ▼
        Django ORM / SQLite              Pure simulation engine (no Django)
                                          engine.py · propagation.py · risk.py · recommendations.py
```

The simulation engine works on immutable dataclasses (`simulation/domain.py`) and never touches the database. `simulation/services.py` builds the engine input from the database, runs it, and persists the results atomically. See [docs/architecture.md](docs/architecture.md) for the diagrams.

## Prerequisites

- Python **3.12+** (`python --version`)
- Git
- About 300 MB of disk space for the virtual environment (Matplotlib and NumPy)

## Installation

### Windows (PowerShell)

```powershell
git clone <your-repo-url> codeguard
cd codeguard
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements-dev.txt   # or requirements.txt for runtime only
Copy-Item .env.example .env           # then edit DJANGO_SECRET_KEY
```

### Linux / macOS (bash or zsh)

```bash
git clone <your-repo-url> codeguard
cd codeguard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env                  # then edit DJANGO_SECRET_KEY
```

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Environment configuration

Settings are read from environment variables. A local `.env` file is loaded automatically and is git-ignored.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Set to `true` for local development only |
| `DJANGO_SECRET_KEY` | *(required when DEBUG is false)* | Cryptographic signing key; never commit it |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` in DEBUG, empty otherwise | Comma-separated host names |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | e.g. `https://codeguard.example.edu` |
| `CODEGUARD_DEFAULT_ROLE` | `analyst` | Role for self-registered users: `analyst` or `viewer` (never admin) |
| `CODEGUARD_REGISTRATION` | `open` | `open`, `domain` (with `CODEGUARD_REGISTRATION_DOMAINS`) or `closed`. Use `domain` or `closed` on any reachable deployment |
| `CODEGUARD_LOGIN_MAX_FAILURES`, `CODEGUARD_LOGIN_IP_MAX_FAILURES`, `CODEGUARD_LOGIN_LOCKOUT_MINUTES` | `5`, `20`, `15` | Sign-in throttling |
| `CODEGUARD_LOG_FORMAT` | `text` | `json` for one JSON object per log line |
| `DJANGO_EMAIL_BACKEND`, `DJANGO_EMAIL_HOST`, … | console backend | Password-reset email (see [docs/deployment.md](docs/deployment.md)) |
| `DJANGO_DB_PATH` | `./db.sqlite3` | SQLite file location |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES`, `DJANGO_HSTS_SECONDS`, `DJANGO_BEHIND_PROXY` | secure when DEBUG is false | HTTPS hardening |

## Database, seed data and the first administrator

```bash
python manage.py check
python manage.py migrate
python manage.py seed_codeguard          # safe to run repeatedly
python manage.py createsuperuser         # your administrator account
```

`seed_codeguard` options:

- `--reset-scenarios` restores the six system scenarios to their seeded definitions.
- `--demo-users` creates `demo_admin`, `demo_analyst` and `demo_viewer` with the password **`CodeGuard-demo-2024`**. These are **development-only** accounts: the command refuses to create them unless `DJANGO_DEBUG=true`. Never use them on a shared or production system.

## Run the application

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>, register or sign in, then follow **New simulation**.

## Testing, coverage and linting

```bash
pytest                                   # full suite (uses an isolated temporary database)
pytest --cov --cov-report=term --cov-report=html   # coverage; HTML report in htmlcov/
coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=85
ruff check .                             # lint
ruff format --check .                    # formatting
python manage.py check                   # Django system checks
python manage.py makemigrations --check --dry-run
pip-audit -r requirements.txt            # dependency vulnerability scan (needs internet)
```

To run every gate the Jenkins pipeline runs, use `scripts\ci_local.ps1` (Windows) or `./scripts/ci_local.sh`.

### Last verified results

Last re-verified on 2026-10-26 (engineering review round) on Windows 11 with Python 3.12.10.

| Check | Result |
|---|---|
| `pytest` | **268 passed** |
| Coverage | **96%** total; **99%** on the core engine modules (gate is 85%) |
| Ruff lint/format, `manage.py check`, `makemigrations --check` | Clean |
| `scripts/ci_deploy_check.py` (`check --deploy`) | 0 errors; 2 intentional HSTS warnings, and `codeguard.W001` because the default registration mode is `open` (see Security notes) |
| `scripts/ci_dependency_audit.py` (`pip-audit`) | No known vulnerabilities. Offline behaviour also tested: exit 2 (UNSTABLE) after the 180 s cap. |
| Jenkinsfile commands rehearsed on a clean checkout with a fresh venv (`scripts/rehearse_jenkinsfile.py`) | SUCCESS (not a Jenkins execution; see below) |
| Concurrent writes: 4 processes × 50 simulation runs on one SQLite file | 200/200 completed (Django defaults: 44/200) |
| axe-core 4.10.2, WCAG 2.0/2.1/2.2 A+AA and best practice, 24 pages at 1280px and 390px, light and dark themes | `color-contrast` only (palette, see Accessibility); 0 other violations |
| Validation-error states (5) with axe-core | `color-contrast` only in 4 states; 0 other violations |
| Keyboard: visible focus on every tab stop; skip link first | Passed on all 24 pages |
| Reflow at 390px (no zoom-out or horizontal scroll) | Passed on all 24 pages |
| Browser-driven user journey in real Chrome (keyboard-only key steps) | 14/14 checks passed |
| Remediation workflow in real Chrome (run, add to plan, update, re-run, verified, audited) | 8/8 checks passed |
| Live authorization matrix (second analyst, viewer, anonymous), including remediation items | 52/52 checks passed; database unchanged |

Passing tests do not prove the application is free of vulnerabilities. Automated accessibility checks do not replace testing with a real screen reader, which has **not** been done.

## Jenkins CI/CD

> **Status: the pipeline has not been executed on a Jenkins server.** The development machine has no Jenkins and no Java runtime, and installing that infrastructure was out of scope. What *was* verified:
>
> 1. **Static review.** Two problems that would have broken a real run were fixed:
>    - `UUID.randomUUID()` needs Groovy-sandbox script approval in an SCM-loaded Jenkinsfile.
>    - Fragile string matching of the `pip-audit` JSON could misclassify a vulnerability as a network error.
>
>    Both now live in Python scripts with explicit exit codes, and Jenkins only runs commands.
> 2. **Rehearsal.** `scripts/rehearse_jenkinsfile.py` extracts every command the stages run, in order, from the Jenkinsfile itself and executes them on a clean checkout with a fresh virtual environment. Result: **SUCCESS**.
> 3. **Behaviour checks.** Real deployment check and real `pip-audit` (online and offline), plus unit tests for the CI scripts.
>
> Not verified without Jenkins: Groovy and Declarative syntax parsing, plugin steps (`junit`, `archiveArtifacts`, `recordCoverage`, `timestamps`), `post` blocks, and agent configuration.

**Stages:**

1. **Checkout**
2. **Environment setup:** creates a venv and installs `requirements-dev.txt`.
3. **Static checks:** Ruff lint, Ruff format, `manage.py check`.
4. **Database preparation:** `makemigrations --check`, migrate an isolated CI database, seed twice (idempotency).
5. **Automated tests:** JUnit XML plus coverage XML/HTML.
6. **Coverage gate:** core engine modules ≥ 85%.
7. **Security checks:**
   - `scripts/ci_deploy_check.py` runs `check --deploy` with a random throwaway key.
   - `scripts/ci_dependency_audit.py` exits 0 = clean, 1 = vulnerable (the build **fails**), 2 = advisory service unreachable (the build is **UNSTABLE**, capped at 180 s).

`reports/` is archived after every run. Failing tests or gates fail the build, and no deployment credentials are needed.

### How to run it for real

1. **Commit the code and make it reachable by Jenkins.** Push to GitHub, or another Git server, using the commands under "First commit" below. Jenkins refuses `file://` checkouts of local repositories by default.
2. **Install Jenkins.** Use either option:
   - **Windows (this machine):** install a Java 21 JRE, then Jenkins LTS from <https://www.jenkins.io/download/> (Windows installer). The Jenkins service account must be able to run `python`, but this machine's Python is installed **per-user** and is not on `PATH`. Either reinstall Python 3.12 "for all users" with "Add to PATH" ticked, or set `PATH+PYTHON=C:\Users\PC\AppData\Local\Programs\Python\Python312` under *Manage Jenkins → Nodes → Built-In Node → Configure → Environment variables*.
   - **Docker** (Docker Desktop is installed here): `docker run -d --name codeguard-jenkins -p 8080:8080 -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts-jdk21`. That image has no Python, so add a Linux agent, or build a derived image that runs `apt-get install -y python3 python3-venv`. Check that `python3 --version` reports **3.12 or newer**: the project declares `requires-python >=3.12` and was verified only on 3.12.10.
3. **Unlock Jenkins.** Open <http://localhost:8080> and use the initial admin password (`docker exec codeguard-jenkins cat /var/jenkins_home/secrets/initialAdminPassword`, or the file shown by the installer). Install the **suggested plugins**, then make sure **Pipeline**, **Git**, **JUnit** and **Timestamper** are present. **Coverage** is optional; the pipeline skips that step cleanly without it.
4. **Lint the Jenkinsfile on the server.** This step has never been performed. Use the Jenkins CLI (`java -jar jenkins-cli.jar -s http://localhost:8080/ -auth USER:API_TOKEN declarative-linter < Jenkinsfile`), or post the file to `http://localhost:8080/pipeline-model-converter/validate` (form field `jenkinsfile`, authenticated with an API token).
5. **Create the job.** *New Item → Pipeline → Pipeline script from SCM → Git*: enter the repository URL (plus credentials if private), set the branch to `*/main`, and the Script Path to `Jenkinsfile`.
6. **Build Now.** Expect the seven stages above. Check the *Test Result* page (JUnit) and the archived `reports/`.

## Accessibility

The app was audited against WCAG 2.2 AA with automated tools and, in its original dark theme, fixed until every check passed. The audit covered 24 pages, 5 error states, keyboard focus and reflow. Fixes made during the audit:

**Open after the paper-theme redesign (2026-10-26):** the DESIGN.md palette fails WCAG AA text contrast in four pairs (white on `--accent` 4.38:1; `--sev-low`, `--sev-med`, `--sev-high` on their tints 4.30, 3.59 and 4.27:1), so axe now reports `color-contrast` on 20 of 22 audited pages. All other checks still pass.

**Dark mode (2026-10-26):** in the dark theme the only failing pair is white on the dark `--accent` (3.58:1, the primary button); every badge, table, form and the audit log pass. Audit both themes with `npm run audit` and `CODEGUARD_THEME=dark npm run audit` (report: `audit-report-dark.json`).

- **Contrast (original dark theme, superseded).** Primary buttons darkened from 3.7:1 to 5.4:1.
- **Error announcements.** Form errors are now linked to their fields (`aria-invalid` with `aria-describedby` pointing to the error text). Previously the referenced IDs didn't exist.
- **No context change on input.** Selects no longer auto-submit (WCAG 3.2.2); every filter has a submit button.
- **Reflow at 390px.** Absolutely positioned hidden labels inside tables no longer widen the page, which had made phones zoom out.
- **Reachable scroll areas.** Wide tables and the diagram are named, keyboard-focusable regions whenever they scroll.
- **Names and roles.**
  - Every data table has an accessible name.
  - The pipeline diagram has a short name plus a stage-by-stage description.
  - Charts have text alternatives that include the plotted numbers.
  - Navigation has `aria-current`, the decorative legend symbols are hidden, and messages are announced politely or assertively as appropriate.

Remaining limitation: no testing with a real screen reader (NVDA, JAWS or VoiceOver) has been done. See `tools/a11y/README.md` to rerun the browser checks.

## Verification tools (optional)

- `scripts/rehearse_jenkinsfile.py` runs the Jenkinsfile's commands on a clean checkout.
- `tools/a11y/` holds the Node 22+ browser checks using axe-core (`npm install`, then `npm run journey`, `npm run audit` and `npm run errors`).
- `tools/authz_live.py` runs the live authorization matrix.

None of these are needed to run the app. Instructions are in `tools/a11y/README.md`.

## Simulation methodology (summary)

1. The entry stage is compromised by assumption, at the scenario's base likelihood. Preventive controls on that stage reduce this likelihood.
2. Each outgoing edge of a compromised stage is evaluated once (breadth-first and cycle-safe):
   `effective probability = edge probability × (1 − preventive coverage of target / 100)`
3. The edge propagates when `effective probability ≥ threshold` (50% by default). Otherwise the target is **blocked** (controls made the difference) or **exposed** (the edge was below the threshold anyway).
4. Stage likelihood is the most likely successful path, i.e. the product of effective probabilities along it.
5. Risk is calculated as follows:
   - `Raw risk = likelihood × (severity/5) × (impact/5)`
   - `Residual risk = raw risk × (1 − mitigating coverage/100)`. Detective and recovery controls mitigate; preventive controls act on propagation.
   - `Combined coverage = 1 − ∏(1 − eᵢ)`, which assumes the controls are independent.
   - `Overall risk = Σ(weight × stage risk) / Σ weight`. The stage weights are IDE 1, VCS 2, CI/CD 2, Registry 2, Production 3.
6. All scores are clamped to 0–100 and rounded half-up to 0.1. The risk classes are: Low < 15 ≤ Moderate < 30 ≤ High < 50 ≤ Critical.

Read the in-app **Methodology** page or [docs/architecture.md](docs/architecture.md) for details and limitations.

## Security notes and limitations

- Authentication uses Django's own hashers, sessions, CSRF protection and password validators. Logout requires a POST request.
- Every sensitive view checks the user's role and object ownership on the server. Another user's private objects return 404, so their IDs are never confirmed.
- A strict Content Security Policy is applied, with no inline scripts and only same-origin assets. The app also sets `X-Frame-Options: DENY`, `nosniff` and `Referrer-Policy`.
- When `DEBUG` is off, the app turns on HTTPS redirect, secure cookies and HSTS, and requires `DJANGO_SECRET_KEY`. Deploy behind HTTPS only.
- `check --deploy` leaves two intentional warnings: HSTS subdomains and preload. Enable them only if you control every subdomain.
- Sign-in is throttled (5 failures per username or 20 per IP within 15 minutes) and every throttled attempt is audited.
- The deployment is the tenancy boundary: "shared" means every account on this instance. Set `CODEGUARD_REGISTRATION` to `domain` or `closed` on any reachable deployment; `check --deploy` warns (`codeguard.W001`) otherwise.
- Known limitations:
  - SQLite is tuned for a single host with a few workers (WAL, immediate transactions); beyond that, move to PostgreSQL (see [docs/architecture.md](docs/architecture.md), section 9).
  - Audit immutability is enforced by the application, not by the database.
  - The model's numbers are illustrative.

An engineering review with prioritized findings and their status is in [docs/engineering-assessment.md](docs/engineering-assessment.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | Create `.env` from `.env.example` with `DJANGO_DEBUG=true`, or set a secret key. |
| Pages load without styling | `DJANGO_DEBUG` must be `true` for `runserver` to serve static files. In production, run `collectstatic` and serve `staticfiles/` with the web server. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call `.\.venv\Scripts\python.exe` directly. |
| Threat library is empty | Run `python manage.py seed_codeguard`. |
| 403 when running a simulation | Your role is Viewer. Ask an administrator to make you an Analyst (Users & roles page). |
| Password reset email does not arrive | Locally it is printed in the terminal running `runserver`. |
| `pip-audit` fails in CI | It needs internet access to the PyPI advisory database. `scripts/ci_dependency_audit.py` exits 2 (UNSTABLE) in that case. |
| Template edits don't appear | Django caches templates. `runserver` reloads automatically, unless it was started with `--noreload`, in which case restart it. |

## Project structure

```
codeguard/            Django project (settings, test_settings, urls, wsgi/asgi)
accounts/             roles (Profile), registration policy, sign-in throttling, permissions, role management
threats/              stages, controls, scenarios, rules; library views; seed command
simulation/           engine (domain, engine, propagation, risk, recommendations, serialization),
                      persistence (models, services), views, charts, visual (SVG), exports (CSV)
remediation/          remediation plan: items from recommendations, status, verification
audit/                append-only audit events, sanitising service, log view, retention command
core/                 landing, dashboard, methodology, error handlers, CSP and request-ID middleware,
                      logging, health check, backup command, template tags
templates/            base layout, components, and per-app pages
static/               css/codeguard.css, js/app.js, vendor/ (Bootstrap, icons), images/
docs/                 requirements, architecture, threat model, data dictionary, test plan, user guide,
                      deployment guide, engineering assessment
tests/                cross-app integration tests
scripts/              ci_local.ps1 / ci_local.sh, ci_deploy_check.py, ci_dependency_audit.py,
                      rehearse_jenkinsfile.py
tools/                optional verification: a11y/ (axe-core browser audit, keyboard journey), authz_live.py
Jenkinsfile, .github/ CI pipelines
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch naming, commit and pull request conventions and the milestone plan.

## First commit

The repository has been initialised, but nothing has been committed yet. Set your identity, then commit:

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
git add -A
git commit -m "CodeGuard: initial implementation"
```
