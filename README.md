# CodeGuard: Application Security and Software Supply-Chain Security Platform

CodeGuard is a Django-based application security and software supply-chain security platform. It helps security teams understand potential attack paths, identify weaknesses in uploaded source code, review security findings and track remediation. Every score, decision and recommendation in the threat simulations is produced by documented, deterministic rules you can inspect.

CodeGuard combines three main capabilities:

1. **Software supply-chain threat modelling and simulation**: how a compromise propagates from a developer environment to production (five-stage graph).
2. **Application-level security threat modelling and simulation**: how untrusted input can reach vulnerable application components and affect downstream systems (six-stage graph).
3. **Static source-code security analysis powered by GitHub CodeQL**: upload a ZIP archive of Python, JavaScript or TypeScript source, review the findings, and track remediation.

> CodeGuard is designed for security awareness, analysis, threat modelling and defensive security assessment. Its threat simulations are hypothetical models whose numbers are illustrative. **CodeGuard performs static analysis of uploaded source code. It does not execute the uploaded application or attempt to exploit it**, and it never attacks or connects to real systems. It is not a replacement for a professional security assessment.

## Table of contents

- [Quick start](#quick-start-run-it-on-your-own-pc)
- [Key concepts](#key-concepts)
- [Features](#features)
- [Information architecture](#information-architecture)
- [Technology stack](#technology-stack)
- [Architecture summary](#architecture-summary)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment configuration](#environment-configuration)
- [CodeQL Installation and Configuration](#codeql-installation-and-configuration)
- [Database, seed data and the first administrator](#database-seed-data-and-the-first-administrator)
- [Threat catalogue](#threat-catalogue)
- [Run the application](#run-the-application)
- [Running a Static Code Analysis Scan](#running-a-static-code-analysis-scan)
- [Security and privacy of uploaded source code](#security-and-privacy-of-uploaded-source-code)
- [Testing, coverage and linting](#testing-coverage-and-linting)
- [Jenkins CI/CD](#jenkins-cicd)
- [Accessibility](#accessibility)
- [Verification tools](#verification-tools-optional)
- [Simulation methodology](#simulation-methodology-summary)
- [Security notes](#security-notes)
- [Limitations](#limitations)
- [Roadmap](#roadmap-planned-not-implemented)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [First commit](#first-commit)

## Quick start (run it on your own PC)

You need **Python 3.12 or newer** (`python --version`) and Git. Run these in order; the app then runs at <http://127.0.0.1:8000/>.

This gets the threat modelling and simulation features running. **Static code scanning additionally needs the CodeQL CLI**, which is installed separately: see [CodeQL Installation and Configuration](#codeql-installation-and-configuration).

**Windows (PowerShell)**

```powershell
git clone https://github.com/bsclmr111626/software-engineering-project.git codeguard
cd codeguard
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_codeguard --demo-users
python manage.py seed_application_threats
python manage.py runserver
```

**Linux / macOS**

```bash
git clone https://github.com/bsclmr111626/software-engineering-project.git codeguard
cd codeguard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_codeguard --demo-users
python manage.py seed_application_threats
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with a demo account. All three share the password `CodeGuard-demo-2024`:

| Username | Role |
|---|---|
| `demo_admin` | Admin: everything, plus users, organization settings and the audit log |
| `demo_analyst` | Analyst: create scenarios and run simulations |
| `demo_viewer` | Viewer: read-only |

Stop the server with **Ctrl + C**. Next time, only `cd codeguard`, activate the virtual environment and `python manage.py runserver` are needed.

Common problems:

- *`DJANGO_SECRET_KEY must be set`*: the `.env` file is missing. Run the `Copy-Item` / `cp` step.
- *`no such table`*: run `python manage.py migrate`.
- *Installation fails on `numpy` or `matplotlib`*: your Python is older than 3.12.
- *`http://127.0.0.1:8000` does not open*: that address is your own computer, so the server must be running in your own terminal.

The demo accounts are for local use only. Full installation, configuration and deployment details follow below.

## Key concepts

| Term | Meaning in CodeGuard |
|---|---|
| **CodeQL** | GitHub's static-analysis engine. CodeGuard drives the CodeQL CLI to analyse uploaded source code. It is installed separately from the Python dependencies. |
| **SARIF** | Static Analysis Results Interchange Format, a structured JSON format. CodeQL writes its results as SARIF and CodeGuard parses that output. |
| **Code finding** | A potential weakness reported by CodeQL in an uploaded scan (rule, severity, file location, description, guidance). It is **not** proof of exploitation. |
| **Threat simulation** | A deterministic what-if model of an attack path across a graph of stages and controls. It is hypothetical and is **not** run against your code. |
| **Remediation** | A tracked record (status, notes, due date) of the work to fix a code finding, or to adopt a recommended control in a supply-chain simulation. |

Source-code scanning and threat simulation are separate features. A finding can optionally link to a related application threat simulation (see [below](#f-linking-code-findings-to-application-threat-simulations)).

## Features

### A. Software supply-chain threat modelling

A five-stage supply-chain propagation graph (IDE / Developer Environment → Version Control → CI/CD Pipeline → Software Registry → Production) with forward, bypass and reverse edges. It models threats such as:

- Compromised CI/CD pipelines.
- Compromised developer accounts.
- Compromised software registries.
- Compromised version-control accounts.
- Malicious dependencies.
- Production credential exposure.

A **scenario** defines the entry stage and the likelihood of compromise. **Stages** carry assets and impact ratings. **Security controls** (preventive, detective, recovery) reduce propagation probability or residual risk. The deterministic engine walks the graph from the entry stage, and a stage is reached only when the effective probability of the edge, after the controls on the target, meets the threshold. See [Simulation methodology](#simulation-methodology-summary).

Supporting capabilities:

- **Threat library**: six seeded teaching scenarios plus private custom scenarios (create, edit with versioning, archive, delete, clone), with search, filters and pagination.
- **Explainable risk scoring**: inherent vs residual risk per stage and overall, with plain-language reasoning for every stage and edge.
- **Security control catalog**: 14 controls. Each states the assumption behind its illustrative effectiveness value and what it does not cover.
- **Recommendations**: each is computed by re-running the model with the control added, so it reports the exact modeled reduction.
- **Before/after comparison**: rerun with different controls and compare runs stage by stage.
- **Remediation plan**: add a recommended control to a private plan, track status, due date and notes, and see it verified when a later run with the control enabled confirms the modeled reduction.
- **Historical reports**: immutable, versioned snapshots; CSV export; optional read-only sharing.

### B. Application-level threat modelling

CodeGuard also supports a **separate** application-security threat graph with six stages:

1. External Input
2. Application
3. Operating System
4. Database
5. File System
6. Deserialization

Four application-security scenarios are currently implemented:

- Application Command Injection
- Application Insecure Deserialization
- Application Path Traversal
- Application SQL Injection

These scenarios model how untrusted input can reach vulnerable application components and potentially affect downstream systems. The application graph is **not** the supply-chain graph: they are different graph types with their own stages, controls and scenarios (see [Threat catalogue](#threat-catalogue)).

### C. Static source-code security analysis using CodeQL

Authenticated users can upload a source-code ZIP archive for static security analysis. Supported languages:

- Python
- JavaScript
- TypeScript

The scanning process:

1. The user uploads a source-code ZIP archive.
2. CodeGuard validates the archive and its contents.
3. The application extracts eligible source files into a controlled temporary workspace.
4. CodeGuard identifies the supported programming language.
5. CodeQL creates a language-specific analysis database.
6. CodeQL executes the relevant security query suite.
7. CodeQL produces SARIF output.
8. CodeGuard parses the SARIF results.
9. Findings are stored in the application's database.
10. The user reviews the findings through the CodeGuard interface.

Findings include, where available, severity, rule identifiers, file locations, descriptions and remediation guidance. Users can open individual scans and view the findings associated with each.

### D. SARIF support

CodeGuard processes the SARIF output produced by CodeQL. SARIF is the structured exchange format between CodeQL and CodeGuard. The parser is written for CodeQL output; CodeGuard does not claim to support arbitrary SARIF producers.

### E. Finding remediation and tracking

For code findings, users can:

- Review identified findings.
- Read recommended remediation guidance.
- Track remediation status.
- Add remediation notes.
- Set due dates where supported.
- Review remediation progress.

A remediation record is attached to a single code finding and holds the status, notes and due date for it, while the finding itself keeps the CodeQL result data. Supply-chain remediation (controls added to a plan) is a separate, existing workflow.

### F. Linking code findings to application threat simulations

Certain recognised CodeQL findings can provide a link to a related application threat simulation.

| CodeQL finding | Related application scenario |
|---|---|
| Python command-line injection | Application Command Injection |
| JavaScript command-line injection | Application Command Injection |
| JavaScript SQL injection | Application SQL Injection |
| JavaScript path injection | Application Path Traversal |

Supported CWE tags can be used as a fallback for mapping findings to scenarios.

Limitations of the mapping:

- Not every CodeQL finding has a matching application threat scenario.
- Findings without a supported mapping do not display a threat-simulation action.
- JavaScript code injection is **not** automatically classified as insecure deserialization.
- Missing-rate-limiting findings are not currently mapped to an application scenario.
- The simulation is a hypothetical threat model, not proof that the uploaded application has been exploited.

### G. Product shell, reporting and operations

- **Multi-page product shell**: a sidebar organised the way an analyst works (Overview; Model: Supply chain, Threat library, Security controls; Simulate: Simulations, Results; Analyze and respond: Risk analysis, Remediation; Records: Reports, Activity and audit), breadcrumbs, a notifications inbox and an account menu. See [Information architecture](#information-architecture).
- **Supply chain explorer**: the five stages with their assets, protecting controls, entry scenarios, a propagation graph aggregated across scenarios, and per-stage history.
- **Results workspace**: each run opens on a summary (headline risk, plain-language explanation, propagation diagram, top recommendations, affected assets) with tabs for stage analysis, every evaluated path, controls and recommendations, and inputs and method. Any run can also be opened as a printable assessment document.
- **Risk analysis**: inherent vs residual trend, exposure by stage, the average effect of each control, and run comparison.
- **Charts**: inline SVG charts drawn from the design tokens (each with a text description, keyboard tooltips and a data table) plus Matplotlib charts for per-run detail.
- **Overview**: live metrics from the database, with empty states; nothing is hardcoded.
- **Roles**: Administrator, Analyst and Viewer, enforced on the server, plus object ownership.
- **Audit log**: append-only (single and bulk changes refused) and sanitised (never stores passwords or tokens), with a retention command.
- **Security hardening**: sign-in throttling, a registration policy (open, allowed email domains, or closed), strict CSP, security headers, CSRF, IDOR protection, secure cookie settings, and friendly error pages.
- **Operations**: `/healthz/` health check, request IDs on every response and log line, optional JSON logs, online verified backups (`backup_db`), and a [deployment guide](docs/deployment.md).
- **Settings center**: Profile, Account, Appearance and theme (light, dark or system; three accent themes), Text and typography, Display, Accessibility, Notifications, Privacy and data (including JSON export of your data), Password and security, Sessions, and for administrators Organization and Users and roles. Every setting is stored per user and changes behaviour.
- **Design system**: an editorial identity (warm paper, graphite ink, an ultramarine signal colour; Newsreader, Instrument Sans and JetBrains Mono) defined as CSS tokens, with light and dark themes. See [DESIGN.md](DESIGN.md).
- **Accessibility**: WCAG 2.2 AA automated audit (axe-core) of 47 pages at desktop and phone widths in both themes with 0 violations.
- **Tests and CI**: an automated test suite, a Jenkins pipeline, GitHub Actions, Ruff, and optional browser-based verification tools.

## Information architecture

| Area | URL | Purpose |
|---|---|---|
| Landing | `/` | Public product page: problem, capabilities, how simulations work, roles. Its figures are live counts. |
| Overview | `/overview/` | Key figures, average residual risk by class, next actions, where compromises land, recent activity. |
| Supply chain | `/supply-chain/`, `/supply-chain/<stage>/` | Stages, assets, controls, entry scenarios, aggregated propagation graph, per-stage history. |
| Threat library | `/threats/` | Searchable, filterable scenario management (tabs: active, my private, archived). |
| Security controls | `/threats/controls/` | Control catalog by category and protected stage. |
| Simulations | `/simulations/`, `/simulations/new/` | Start from a scenario (grouped by entry stage); a four-step configuration workflow. |
| Results | `/simulations/results/`, `/simulations/<id>/` plus `stages/`, `paths/`, `controls/`, `method/` | Result cards with stage strips; a tabbed results workspace per run. |
| Risk analysis | `/risk/`, `/simulations/compare/` | Trends, exposure by stage, control effect, run comparison. |
| Remediation | `/remediation/` | Plan with status tabs, prioritisation (due date, modeled reduction, recency) and verification. |
| Reports | `/reports/`, `/reports/<id>/` | Archive of every run, CSV exports, printable assessment documents. |
| Activity and audit | `/audit/` | Activity timeline grouped by day, and the full audit table. |
| Code scans | `/code-scans/` | List of your uploaded source-code scans (route name `code_scans:list`). |
| Upload a scan | `/code-scans/upload/` | Upload a source-code ZIP archive for CodeQL analysis (`code_scans:upload`). |
| Scan detail | `/code-scans/<scan_id>/` | One scan and its findings; `<scan_id>` is a UUID (`code_scans:detail`). |
| Notifications | `/notifications/` | Shared reports, remediation deadlines and account security events. |
| Settings | `/settings/...` | Profile, account, appearance, typography, display, accessibility, notifications, privacy, security, sessions; organization and users for administrators. |

The code-scanning routes are defined in `code_scans/urls.py` (app name `code_scans`) and are served under `/code-scans/`.

`/dashboard/` and `/accounts/users/` redirect to their new locations.

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS, Django ORM, auth and sessions |
| Database | SQLite (default backend) |
| Frontend | Django templates, HTML, CSS and vanilla JavaScript; Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 (vendored locally) |
| Charts | Matplotlib (Agg backend, rendered in memory) |
| Static analysis | GitHub CodeQL CLI, CodeQL Python query pack (`codeql/python-queries`), CodeQL JavaScript query pack (`codeql/javascript-queries`), SARIF output |
| Quality | pytest, pytest-django, pytest-cov / Coverage.py, Ruff, pip-audit |
| CI/CD | Jenkins Declarative Pipeline (`Jenkinsfile`); GitHub Actions as a supplement |

CodeGuard does not use Redis, Celery, Docker or PostgreSQL as required components. (PostgreSQL is mentioned only as a possible future move for larger deployments; see [docs/architecture.md](docs/architecture.md).)

## Architecture summary

```
Browser ──► Django views (accounts, threats, simulation, code_scans, remediation, audit, core)
               │  forms validate input · permissions checked server-side
               ▼
           Service layer (threats/, simulation/, code_scans/services/, audit/ services)
               │                          │                       │
               ▼                          ▼                       ▼
        Django ORM / SQLite     Pure simulation engine     CodeQL CLI (subprocess)
                                (no Django)                → SARIF → parsed findings
```

The simulation engine works on immutable dataclasses (`simulation/domain.py`) and never touches the database. `simulation/services.py` builds the engine input from the database, runs it, and persists the results atomically. Code scans run the CodeQL CLI synchronously from the service layer and store the parsed SARIF findings in the database. See [docs/architecture.md](docs/architecture.md) for the diagrams.

## Prerequisites

- Python **3.12+** (`python --version`)
- Git
- About 300 MB of disk space for the virtual environment (Matplotlib and NumPy)
- **For static code scanning only:** the CodeQL CLI and query packs (roughly 400 MB to 1 GB of disk space, depending on the OS download). See [CodeQL Installation and Configuration](#codeql-installation-and-configuration).

## Installation

### Windows (PowerShell)

```powershell
git clone https://github.com/bsclmr111626/software-engineering-project.git codeguard
cd codeguard
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements-dev.txt   # or requirements.txt for runtime only
Copy-Item .env.example .env           # optional for local use: set your own DJANGO_SECRET_KEY
```

### Linux / macOS (bash or zsh)

```bash
git clone https://github.com/bsclmr111626/software-engineering-project.git codeguard
cd codeguard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env                  # optional for local use: set your own DJANGO_SECRET_KEY
```

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then install CodeQL (next sections) if you want to use static code scanning.

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
| `CODEQL_EXECUTABLE` | see `codeguard/settings.py` | Full path to the CodeQL CLI executable. See [below](#e-configure-the-codeql-executable). |

## CodeQL Installation and Configuration

### A. The CodeQL dependency

CodeGuard requires the **CodeQL CLI** to perform static source-code analysis. Installing Python packages with `pip` does **not** install the CodeQL CLI. You must separately:

1. Download and extract the CodeQL CLI for your operating system.
2. Download the CodeQL query packs for the languages you want to scan.
3. Tell CodeGuard where the executable is (`CODEQL_EXECUTABLE`).

Official documentation:

- CodeQL documentation: <https://codeql.github.com/docs/>
- CodeQL CLI documentation: <https://docs.github.com/en/code-security/codeql-cli>
- CodeQL CLI releases: <https://github.com/github/codeql-cli-binaries/releases>

> Check GitHub's applicable licensing and usage terms for your intended CodeQL deployment before using it, particularly outside open-source or research use.

**Versions.** CodeGuard does not pin a CodeQL version. CodeQL CLI releases and query-pack versions are published regularly, so install the latest release unless you need a specific one. After installing or upgrading, run the [verification steps](#i-verify-the-installation) and the code-scan tests to confirm everything still works.

### B. Choose the right download for your OS

Open the latest release page, <https://github.com/github/codeql-cli-binaries/releases/latest>, and download the ZIP that matches your machine:

| Your system | Asset to download |
|---|---|
| **Windows (64-bit)** | `codeql-win64.zip` |
| **Linux (x86-64)** | `codeql-linux64.zip` |
| **Linux (ARM64)** | `codeql-linux-arm64.zip` |
| **macOS** | `codeql-osx64.zip` |

Asset names stay the same between releases. Each ZIP has a matching `.checksum.txt` file on the release page, and the release page lists the current file sizes and SHA-256 values.

Verify the download against the published checksum before extracting:

```powershell
# Windows
Get-FileHash .\codeql-win64.zip -Algorithm SHA256
```

```bash
# Linux
sha256sum codeql-linux64.zip
# macOS
shasum -a 256 codeql-osx64.zip
```

The output must match the value published for that release.

### C. Windows installation

The exact extracted directory may differ depending on the downloaded archive and where you extract it. This guide uses `C:\CodeQL\codeql-win64\codeql\codeql.exe`.

```powershell
New-Item -ItemType Directory -Force C:\CodeQL | Out-Null
Expand-Archive -Path "$HOME\Downloads\codeql-win64.zip" -DestinationPath C:\CodeQL\codeql-win64
& "C:\CodeQL\codeql-win64\codeql\codeql.exe" version
```

If `codeql.exe` is not at that path, look inside the extracted folder (for example with `Get-ChildItem C:\CodeQL -Recurse -Filter codeql.exe`) and use the real location everywhere below.

### D. Linux installation

Use `codeql-linux64.zip` on x86-64 or `codeql-linux-arm64.zip` on ARM64 machines (`uname -m` prints `x86_64` or `aarch64`).

```bash
sudo mkdir -p /opt/codeql
sudo unzip ~/Downloads/codeql-linux64.zip -d /opt/codeql    # or codeql-linux-arm64.zip
/opt/codeql/codeql/codeql version
```

Replace `/opt/codeql/codeql/codeql` with the location where you extracted CodeQL if it differs. Make sure the user running CodeGuard can read and execute that directory.

### E. macOS installation

```bash
mkdir -p ~/codeql
unzip ~/Downloads/codeql-osx64.zip -d ~/codeql
~/codeql/codeql/codeql version
```

If macOS blocks the binary because it was downloaded from the internet, remove the quarantine attribute and try again: `xattr -dr com.apple.quarantine ~/codeql/codeql`. On Apple Silicon Macs, check GitHub's CodeQL CLI documentation for the current guidance on running the macOS build.

### F. Download the CodeQL query packs

Both packs are required:

- **Python queries** analyse Python source code.
- **JavaScript queries** analyse JavaScript **and** TypeScript source code.

Windows (PowerShell):

```powershell
& "C:\CodeQL\codeql-win64\codeql\codeql.exe" pack download codeql/python-queries

& "C:\CodeQL\codeql-win64\codeql\codeql.exe" pack download codeql/javascript-queries
```

Linux:

```bash
/opt/codeql/codeql/codeql pack download codeql/python-queries

/opt/codeql/codeql/codeql pack download codeql/javascript-queries
```

macOS: use the same commands with `~/codeql/codeql/codeql`. Downloading packs needs internet access.

The current implementation uses the following security query suites (they come with the packs above):

```text
codeql/python-queries:codeql-suites/python-security-extended.qls
codeql/javascript-queries:codeql-suites/javascript-security-extended.qls
```

> Verify these against `code_scans/services/` in your checkout; the suites used by the code are authoritative.

### G. Configure the CodeQL executable

`CODEQL_EXECUTABLE` tells CodeGuard where the CodeQL CLI executable is. It must point at the **executable file**, not the installation directory.

Add it to `.env`:

```env
# Windows
CODEQL_EXECUTABLE=C:\CodeQL\codeql-win64\codeql\codeql.exe
```

```env
# Linux
CODEQL_EXECUTABLE=/opt/codeql/codeql/codeql
```

```env
# macOS
CODEQL_EXECUTABLE=/Users/<you>/codeql/codeql/codeql
```

Restart the development server after changing `.env`. If the variable is not set, CodeGuard uses the default defined in `codeguard/settings.py`; check that file to see what the default path is on your version.

### H. Scan limits

The scan limits protect the application against excessively large or resource-intensive uploads. The current defaults in the development configuration are:

| Setting | Current default |
|---|---:|
| Maximum ZIP upload size | 25 MB |
| Maximum extracted source size | 100 MB |
| Maximum extracted files | 5,000 |
| CodeQL timeout | 900 seconds |

These values are defined in `codeguard/settings.py`. To change them, edit the corresponding settings there (use the setting names defined in that file). They are not documented here as `.env` variables because that has not been confirmed.

### I. Verify the installation

Windows:

```powershell
& "C:\CodeQL\codeql-win64\codeql\codeql.exe" version

& "C:\CodeQL\codeql-win64\codeql\codeql.exe" resolve packs

python manage.py check
```

Linux / macOS (adjust the path):

```bash
/opt/codeql/codeql/codeql version
/opt/codeql/codeql/codeql resolve packs
python manage.py check
```

What success looks like:

- `version` prints the installed CodeQL CLI version.
- `resolve packs` lists `codeql/python-queries` and `codeql/javascript-queries` among the available packs.
- `python manage.py check` prints `System check identified no issues (0 silenced).`

### J. CodeQL troubleshooting

| Problem | Likely cause and what to try |
|---|---|
| CodeQL executable not found | CodeQL is not installed, or the path is wrong. Run the `version` command by hand. |
| Invalid `CODEQL_EXECUTABLE` path | The value points to a folder, has a typo, or is not in `.env`. Point it at the executable file itself, then restart the server. |
| Query pack missing | The packs were not downloaded. Run `pack download` for both packs, then check `resolve packs`. |
| Query suite not found | The pack version installed does not contain the suite the code asks for, or the pack was not found. Compare `resolve packs` and the suite names above. |
| CodeQL execution timeout | The project is too large or the machine too slow. Scan a smaller archive, or raise the timeout in `codeguard/settings.py`. |
| Unsupported source-code language | The archive has no Python, JavaScript or TypeScript source. Only those are supported. |
| Invalid or unsafe ZIP archive | The file is not a valid ZIP, is corrupt, exceeds the size or file-count limits, or contains unsafe paths. Rebuild the ZIP from your source tree. |

Read the message CodeGuard shows for a failed scan together with the console output of `runserver`; both help to narrow down which of the causes above applies.

## Database, seed data and the first administrator

For a fresh install, initialise the database with:

```powershell
python manage.py check
python manage.py migrate
python manage.py seed_codeguard
python manage.py seed_application_threats
python manage.py createsuperuser         # your administrator account
```

- `seed_codeguard` initialises the software supply-chain security catalogue.
- `seed_application_threats` initialises the application-security stages, controls and scenarios. `seed_codeguard` does **not** run it for you, so run both commands to get the complete catalogue.
- Both are intended to be safe to run repeatedly. (Confirm `seed_application_threats` idempotency in its source before relying on that in automation.)

`seed_codeguard` options:

- `--reset-scenarios` restores the six system scenarios to their seeded definitions.
- `--demo-users` creates `demo_admin`, `demo_analyst` and `demo_viewer` with the password **`CodeGuard-demo-2024`**. These are **development-only** accounts: the command refuses to create them unless `DJANGO_DEBUG=true`. Never use them on a shared or production system.

## Threat catalogue

The two graph types are separate and are counted separately.

| Category | Stages | Scenarios | Controls |
|---|---:|---:|---:|
| Software supply chain | 5 | 6 | 14 |
| Application security | 6 | 4 | 13 |

## Run the application

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>, register or sign in, then follow **New simulation**, or open the code-scanning section to scan source code.

## Running a Static Code Analysis Scan

Prerequisite: CodeQL and both query packs are installed and `CODEQL_EXECUTABLE` is set (see [CodeQL Installation and Configuration](#codeql-installation-and-configuration)).

1. Sign in to CodeGuard.
2. Open the code-scanning list at `/code-scans/`.
3. Go to `/code-scans/upload/` and upload a ZIP archive containing the source code.
4. Wait while CodeGuard validates and analyses the archive.
5. Open the completed scan from the list (`/code-scans/<scan_id>/`).
6. Review the identified findings.
7. Inspect each finding's severity, rule information, file path and remediation recommendation.
8. Track remediation where necessary.
9. Launch a related application threat simulation when a finding has a supported mapping.

Notes:

- The archive should contain the actual project source files. Avoid an unrelated wrapper directory around the source if the application expects the source at the extracted root; zip the contents of your project folder rather than a folder that contains it, unless you have confirmed the archive layout works.
- Scans currently run **synchronously**: the request completes when the analysis does, so larger projects can take a while. There is no Celery, Redis, queue or background-worker component.
- Code scans live under `/code-scans/`: the list at `/code-scans/`, the upload form at `/code-scans/upload/`, and each scan at `/code-scans/<scan_id>/` (a UUID).

## Security and privacy of uploaded source code

The scanning workflow includes:

- ZIP archive validation.
- Protection against unsafe archive paths and extraction.
- File-count and extracted-size limits (see [Scan limits](#h-scan-limits)).
- CodeQL execution timeouts.
- User ownership and access restrictions for code scans and findings.
- Static analysis only: uploaded application code is not executed.
- No automatic exploitation of uploaded applications.

**CodeGuard performs static analysis of uploaded source code. It does not execute the uploaded application or attempt to exploit it.**

Interpret the results with care:

- CodeQL findings indicate **potential** security weaknesses.
- A finding is not proof of successful exploitation.
- No findings does not guarantee that the application is secure.
- Static analysis can produce false positives and can miss vulnerabilities.
- Validate findings and carry out additional security testing where appropriate.

## Testing, coverage and linting

```powershell
python manage.py check

python -m pytest -q
```

Targeted runs:

```powershell
python -m pytest code_scans/tests -q

python -m pytest simulation/tests -q

python -m pytest remediation/tests -q

python -m pytest threats/tests -q
```

Other quality gates:

```bash
pytest --cov --cov-report=term --cov-report=html   # coverage; HTML report in htmlcov/
coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=85
ruff check .                             # lint
ruff format --check .                    # formatting
python manage.py makemigrations --check --dry-run
pip-audit -r requirements.txt            # dependency vulnerability scan (needs internet)
```

To run every gate the Jenkins pipeline runs, use `scripts\ci_local.ps1` (Windows) or `./scripts/ci_local.sh`.

### Latest verified development result

In the current development state the project completed:

```text
System check identified no issues (0 silenced).

357 passed in 37.58s
```

This is a result from the current development state and may change as the project evolves. The tests use an isolated temporary database; whether the CodeQL-dependent tests need a real CodeQL install depends on how they are written, so check `code_scans/tests`.

The table below is the older verification record from the product redesign round (2026-10-28, Windows 11, Python 3.12.10), kept for the non-pytest checks. Its pytest count (332) predates the code-scanning work.

| Check | Result |
|---|---|
| Ruff lint/format, `manage.py check`, `makemigrations --check` | Clean |
| `scripts/ci_deploy_check.py` (`check --deploy`) | 0 errors; 2 intentional HSTS warnings, and `codeguard.W001` because the default registration mode is `open` |
| `scripts/ci_dependency_audit.py` (`pip-audit`) *(2026-10-26)* | No known vulnerabilities |
| Jenkinsfile commands rehearsed on a clean checkout (`scripts/rehearse_jenkinsfile.py`) *(2026-10-26)* | SUCCESS (not a Jenkins execution) |
| axe-core 4.10.2, WCAG 2.0/2.1/2.2 A+AA, 47 pages at 1280px and 390px, light and dark | **0 violations** |
| Browser-driven user journey in real Chrome | 14/14 checks passed |
| Live authorization matrix | All checks passed; database unchanged |

Passing tests do not prove the application is free of vulnerabilities. Automated accessibility checks do not replace testing with a real screen reader, which has **not** been done. These figures predate the code-scanning pages; re-run the audits to cover them.

## Jenkins CI/CD

> **Status: the pipeline has not been executed on a Jenkins server.** The development machine has no Jenkins and no Java runtime. What *was* verified:
>
> 1. **Static review.** Two problems that would have broken a real run were fixed: `UUID.randomUUID()` needs Groovy-sandbox script approval in an SCM-loaded Jenkinsfile, and fragile string matching of the `pip-audit` JSON could misclassify a vulnerability as a network error. Both now live in Python scripts with explicit exit codes.
> 2. **Rehearsal.** `scripts/rehearse_jenkinsfile.py` extracts every command the stages run from the Jenkinsfile and executes them on a clean checkout with a fresh virtual environment. Result: **SUCCESS**.
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

> The CI stages above predate code scanning. Confirm that the seeding stage also runs `seed_application_threats` if you want the application catalogue in CI, and note that a CI agent does not need CodeQL unless tests call it.

### How to run it for real

1. **Commit the code and make it reachable by Jenkins.** Push to GitHub, or another Git server, using the commands under "First commit". Jenkins refuses `file://` checkouts of local repositories by default.
2. **Install Jenkins.** Use either option:
   - **Windows:** install a Java 21 JRE, then Jenkins LTS from <https://www.jenkins.io/download/>. The Jenkins service account must be able to run `python`; if Python is installed per-user and not on `PATH`, reinstall it "for all users" with "Add to PATH", or set `PATH+PYTHON` under *Manage Jenkins → Nodes → Built-In Node → Configure → Environment variables*.
   - **Docker:** `docker run -d --name codeguard-jenkins -p 8080:8080 -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts-jdk21`. That image has no Python, so add a Linux agent, or build a derived image that runs `apt-get install -y python3 python3-venv`. Check that `python3 --version` reports **3.12 or newer**.
3. **Unlock Jenkins.** Open <http://localhost:8080> and use the initial admin password (`docker exec codeguard-jenkins cat /var/jenkins_home/secrets/initialAdminPassword`, or the file shown by the installer). Install the **suggested plugins**, then make sure **Pipeline**, **Git**, **JUnit** and **Timestamper** are present. **Coverage** is optional.
4. **Lint the Jenkinsfile on the server.** This step has never been performed. Use the Jenkins CLI (`java -jar jenkins-cli.jar -s http://localhost:8080/ -auth USER:API_TOKEN declarative-linter < Jenkinsfile`), or post the file to `http://localhost:8080/pipeline-model-converter/validate`.
5. **Create the job.** *New Item → Pipeline → Pipeline script from SCM → Git*: enter the repository URL, set the branch to `*/main`, and the Script Path to `Jenkinsfile`.
6. **Build Now.** Expect the seven stages above. Check the *Test Result* page and the archived `reports/`.

## Accessibility

The app was audited against WCAG 2.2 AA with automated tools. The product redesign (2026-10-28) chose the palette with computed contrast: every text pair, including each risk colour on its own tint and the label on the accent, is at least 4.7:1 in both themes. 47 pages pass axe-core with 0 violations in light and dark (`npm run audit`, `CODEGUARD_THEME=dark npm run audit`). Chart marks are focusable with a visible ring and a tooltip, every chart has a "Show as a table" alternative, and Settings > Accessibility adds reduced motion, increased contrast and always-underlined links.

Fixes made during earlier audit rounds:

- **Error announcements.** Form errors are linked to their fields (`aria-invalid` with `aria-describedby`).
- **No context change on input.** Selects no longer auto-submit (WCAG 3.2.2); every filter has a submit button.
- **Reflow at 390px.** Absolutely positioned hidden labels inside tables no longer widen the page.
- **Reachable scroll areas.** Wide tables and the diagram are named, keyboard-focusable regions whenever they scroll.
- **Names and roles.** Every data table has an accessible name; the pipeline diagram has a short name plus a stage-by-stage description; charts have text alternatives with the plotted numbers; navigation has `aria-current`.

Remaining limitation: no testing with a real screen reader (NVDA, JAWS or VoiceOver) has been done. See `tools/a11y/README.md` to rerun the browser checks.

## Verification tools (optional)

- `scripts/rehearse_jenkinsfile.py` runs the Jenkinsfile's commands on a clean checkout.
- `tools/a11y/` holds the Node 22+ browser checks using axe-core (`npm install`, then `npm run journey`, `npm run audit` and `npm run errors`).
- `tools/authz_live.py` runs the live authorization matrix.

None of these are needed to run the app. Instructions are in `tools/a11y/README.md`.

## Simulation methodology (summary)

This describes the supply-chain simulation engine.

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

Read the in-app **Methodology** page or [docs/architecture.md](docs/architecture.md) for details and limitations. Application-security simulations use the application graph and its own controls; see `threats/` and `simulation/` for how they are defined.

## Security notes

- Authentication uses Django's own hashers, sessions, CSRF protection and password validators. Logout requires a POST request.
- Every sensitive view checks the user's role and object ownership on the server. Another user's private objects return 404, so their IDs are never confirmed.
- A strict Content Security Policy is applied, with no inline scripts and only same-origin assets. The app also sets `X-Frame-Options: DENY`, `nosniff` and `Referrer-Policy`.
- When `DEBUG` is off, the app turns on HTTPS redirect, secure cookies and HSTS, and requires `DJANGO_SECRET_KEY`. Deploy behind HTTPS only.
- `check --deploy` leaves two intentional warnings: HSTS subdomains and preload. Enable them only if you control every subdomain.
- Sign-in is throttled (5 failures per username or 20 per IP within 15 minutes) and every throttled attempt is audited.
- The deployment is the tenancy boundary: "shared" means every account on this instance. Set `CODEGUARD_REGISTRATION` to `domain` or `closed` on any reachable deployment; `check --deploy` warns (`codeguard.W001`) otherwise.
- Uploaded source code is handled as described in [Security and privacy of uploaded source code](#security-and-privacy-of-uploaded-source-code). Because scanning runs the CodeQL CLI on the server, restrict who may upload (registration policy and roles) on any shared deployment.

An engineering review with prioritized findings and their status is in [docs/engineering-assessment.md](docs/engineering-assessment.md).

## Limitations

- Static scanning supports Python, JavaScript and TypeScript only.
- CodeQL must be installed and configured separately from CodeGuard.
- Which findings you get depends on the source code, language support, query packs and analysis configuration.
- Not every CodeQL rule has a corresponding application threat simulation.
- Simulations model hypothetical attack paths and do not prove real-world exploitation. The model's numbers are illustrative.
- Static analysis does not replace dynamic testing, manual code review or penetration testing.
- Scans are synchronous, so long-running scans take time to complete and hold the request open.
- SQLite is tuned for a single host with a few workers (WAL, immediate transactions); beyond that, move to PostgreSQL (see [docs/architecture.md](docs/architecture.md), section 9).
- Audit immutability is enforced by the application, not by the database.
- No testing with a real screen reader has been done.

## Roadmap (planned, not implemented)

Nothing in this section is available today. It lists ideas only; edit it to match your actual plans.

- Asynchronous scan execution (a background worker) for long-running scans.
- Additional CodeQL languages and further finding-to-scenario mappings.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | Create `.env` from `.env.example` with `DJANGO_DEBUG=true`, or set a secret key. |
| Pages load without styling | `DJANGO_DEBUG` must be `true` for `runserver` to serve static files. In production, run `collectstatic` and serve `staticfiles/` with the web server. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call `.\.venv\Scripts\python.exe` directly. |
| Threat library is empty | Run `python manage.py seed_codeguard`. |
| Application scenarios or controls are missing | Run `python manage.py seed_application_threats`. |
| Code scan fails immediately | Check `CODEQL_EXECUTABLE` and the [CodeQL troubleshooting table](#j-codeql-troubleshooting). |
| 403 when running a simulation | Your role is Viewer. Ask an administrator to make you an Analyst (Users & roles page). |
| Password reset email does not arrive | Locally it is printed in the terminal running `runserver`. |
| `pip-audit` fails in CI | It needs internet access to the PyPI advisory database. `scripts/ci_dependency_audit.py` exits 2 (UNSTABLE) in that case. |
| Template edits don't appear | Django caches templates. `runserver` reloads automatically, unless it was started with `--noreload`, in which case restart it. |

## Project structure

```
codeguard/            Django project configuration (settings, test_settings, urls, wsgi/asgi)
accounts/             roles (Profile), registration policy, sign-in throttling, permissions, role management
core/                 core application functionality: landing, overview, supply chain, risk analysis,
                      notifications, methodology, error handlers, CSP and request-ID middleware,
                      logging, health check, backup command, template tags
threats/              threat scenarios, stages, controls and catalogues (supply chain and application
                      security); library views; seed commands (seed_codeguard, seed_application_threats)
simulation/           threat simulation execution and reports: engine (domain, engine, propagation, risk,
                      recommendations, serialization), persistence (models, services), views, charts,
                      visual (SVG), exports (CSV)
code_scans/           source-code upload, CodeQL integration, SARIF processing and findings
    services/         archive validation, CodeQL execution, SARIF parsing, finding-to-scenario mapping
    tests/            code-scanning tests
remediation/          remediation guidance and tracking
audit/                append-only audit events, sanitising service, log view, retention command
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

Apps such as `threats/`, `simulation/` and `remediation/` also have their own `tests/` directories. Compare this tree with your checkout before publishing; it is derived from the previous README and the task description.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch naming, commit and pull request conventions and the milestone plan.

## First commit

If nothing has been committed yet, set your identity, then commit:

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
git add -A
git commit -m "CodeGuard: initial implementation"
```