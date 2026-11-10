# CodeGuard — Complete Technical Documentation

**Software Supply Chain Risk Simulator** · documentation generated from the source at commit
`8f5d092` plus the working tree, on 2026-11-10; updated after commits `eef6716` (Reports templates) and `8ca8b36` (CI passing).

This master document gives the whole picture in one read. Each section ends with links to the
detailed documents, which carry the exact formulas, tables and tutorials:

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, apps, design decisions, frontend, request trace, performance |
| [DATABASE_AND_MIGRATIONS.md](DATABASE_AND_MIGRATIONS.md) | SQLite configuration, data model, migrations tutorial on the real files |
| [SECURITY.md](SECURITY.md) | Authentication, sessions, authorization, hardening, audit, gaps |
| [SIMULATION_AND_RISK_METHODOLOGY.md](SIMULATION_AND_RISK_METHODOLOGY.md) | Every formula, a worked numerical example, recommendations |
| [TESTING_AND_QUALITY_ASSURANCE.md](TESTING_AND_QUALITY_ASSURANCE.md) | What was run, what is recorded, what is not covered |
| [DEVELOPMENT_AND_DEPLOYMENT.md](DEVELOPMENT_AND_DEPLOYMENT.md) | Set-up, configuration, Git/GitHub, CI, hosting, troubleshooting |
| [LEARNING_GUIDE.md](LEARNING_GUIDE.md) | A ten-stage study path with exercises |
| [GLOSSARY.md](GLOSSARY.md) | Terms and where the code defines them |
| [diagrams/](diagrams/) | Architecture, request lifecycle, data flow, authentication, simulation workflow, propagation, ERD, CI/CD |
| [references/](references/) | Inventories: models/tables, routes, migrations, dependencies, environment variables, tests |

Earlier project documents in `docs/` (requirements, architecture, data dictionary, threat model,
test plan, user guide, deployment, engineering assessment, redesign acceptance) remain valid and
are cited where relevant; this package does not replace them.

### How to read the status labels

Every feature in this documentation carries one of five labels:

* **Implemented and verified** — code exists and a check passed on 2026-11-10 (the test suite
  in the working tree, or a command run for this documentation).
* **Implemented but unverified** — code exists, but no check was run for this documentation
  (results may be recorded earlier in the README).
* **Partial** — some of the stated capability exists.
* **Planned** — designed or recorded as future work in the project's documents, no code.
* **Not implemented** — absent, and not planned in the repository.

---

## 1. Purpose

**What it is.** CodeGuard is an educational web application that models how a compromise at one
point of a software supply chain can spread to later (or earlier) points, and how security
controls change the outcome. The README states the boundary plainly: it "never scans, attacks or
connects to real systems, its scenarios are hypothetical, and its numbers are illustrative model
outputs".

**Why it exists.** Supply-chain attacks are hard to reason about because the damage depends on
paths between systems, not on any one system. CodeGuard turns that into an explicit, inspectable
graph with deterministic rules, so a student or analyst can ask "what if" and see exactly why the
answer changed.

**How it works, in one paragraph.** An analyst picks a threat scenario (an entry stage, a base
likelihood, severity, impact and a set of directed propagation rules), chooses which security
controls are enabled, and runs a simulation. The engine walks the graph twice, once without
controls (*inherent*) and once with them (*residual*), scores every stage, aggregates an overall
score, explains each decision in plain language, and recommends the controls that would lower
the residual risk most. The run is stored with a complete snapshot of its inputs, rendered as a
report with charts, and can be shared, exported, compared and turned into remediation work.

### 1.1 The five supply-chain stages

Seeded by `threats/seed_data.py` (`STAGES`) and stored in `threats_supplychainstage`:

| Position | Key | Name | Weight | Typical assets (seed text, abbreviated) |
|---|---|---|---|---|
| 1 | `ide` | IDE / Developer Environment | 1 | developer accounts, local checkouts, SSH keys and tokens, IDE extensions |
| 2 | `vcs` | Version Control | 2 | repositories, branches, commits, pull requests, permissions |
| 3 | `cicd` | CI/CD Pipeline | 2 | build jobs, runners, pipeline credentials, release workflows |
| 4 | `registry` | Software Registry | 2 | published packages, container images, publishing credentials |
| 5 | `production` | Production | 3 | deployed services, runtime configuration, production credentials, customer data |

Position orders the stages and classifies edges (forward, bypass, reverse). Weight expresses
criticality in the overall score. Status: **implemented and verified**
(`test_seed_creates_reference_data`).

### 1.2 Feature status overview

| Feature | Status | Evidence / note |
|---|---|---|
| Five-stage model, control catalogue (14), six system scenarios | Implemented and verified | seed tests; seeded on a scratch DB |
| Scenario library: create, edit (versioned), archive/restore, delete, clone, filters | Implemented and verified | `threats/tests/test_scenarios.py` |
| Graph validation (self-loops, duplicates, unreachable rules) in form, engine and schema | Implemented and verified | `test_invalid_graph_rejected`, `TestConstraints`, `TestValidation` |
| Deterministic simulation engine (inherent + residual) | Implemented and verified | 85 engine/risk tests; worked example recomputed by hand |
| Plain-language explanations per stage and per edge | Implemented and verified | `test_explanation_mentions_entry_and_scores` |
| Recommendations and leave-one-out control contributions | Implemented and verified | `test_recommendations.py` |
| Run persistence with reproducible snapshots | Implemented and verified | `test_snapshot_reproduces_the_stored_result` |
| Result pages (summary, stages, paths, controls, method) | Implemented and verified | `test_result_sections_and_report_document` |
| Matplotlib charts (overall, stages, outcomes, comparison, risk distribution) | Implemented and verified | `test_owner_sees_report_with_charts`, palette test |
| SVG pipeline and dashboard/analysis charts | Implemented and verified | `test_pipeline_geometry`, `test_svg_chart_geometry` |
| Run comparison (before/after) | Implemented and verified | `TestComparison` |
| CSV export (run and history) with formula-injection protection | Implemented and verified | `TestReportAccess` |
| Reports area (`/reports/` list and printable document) | Implemented and verified | templates were git-ignored until commit `eef6716`; a fresh clone of that commit passes all 337 tests |
| Report sharing (owner-only toggle, share-by-default preference) | Implemented and verified | `test_shared_report_visible_read_only_to_viewer`, `test_share_by_default_shares_new_reports` |
| Remediation plan with verification by later runs | Implemented and verified | `remediation/tests` |
| Overview dashboard, supply-chain map, stage pages, risk analysis | Implemented and verified | `core/tests/test_core.py`, `test_areas.py` |
| Notifications derived from existing records | Implemented and verified | `test_notifications_from_real_records` |
| Settings: profile, account, appearance, typography, display, accessibility, notifications, privacy, security, sessions, organization, users | Implemented and verified | `accounts/tests/test_settings.py` |
| Three roles with server-side checks; object-level access | Implemented and verified | `TestRoles`, IDOR tests |
| Registration policy (open/domain/closed) and deploy warning | Implemented and verified | `TestRegistrationPolicy`; `ci_deploy_check.py` output |
| Sign-in throttling | Implemented and verified | `TestLoginThrottling` |
| Session revocation ("sign out other sessions") | Implemented and verified | `test_signing_out_other_sessions` |
| Append-only audit trail, retention command | Implemented and verified | `audit/tests` |
| CSP and security headers | Implemented and verified | `test_security_headers_present` |
| Health check, request IDs, JSON logs | Implemented and verified | `core/tests/test_core.py` |
| Online SQLite backup | Implemented and verified (command); restore not automated | `test_backup_db_writes_a_verified_copy_and_rotates` |
| Personal data export (JSON) | Implemented and verified | `test_data_export_contains_only_own_data_and_is_audited` |
| Light/dark themes, accent, surface, text size, density, reduced motion, contrast | Implemented and verified (server side); browser rendering unverified here | `test_preferences_are_rendered_on_the_html_element`, design tests |
| WCAG 2.2 AA automated audit (axe-core, 47 pages) | Implemented but unverified | README records 0 violations (2026-10-28); not re-run |
| Live HTTP authorization matrix | Implemented but unverified | README records "all checks passed"; not re-run |
| GitHub Actions workflow | Implemented and verified | first passing run: run #7 on commit `8ca8b36`, 2026-11-10, 1 min 5 s; runs #1–#6 failed (missing Reports templates, then a Markdown format check) |
| Jenkins pipeline | Implemented but unverified | **never executed on Jenkins**; commands rehearsed only |
| Production deployment guide | Partial | settings and commands tested; proxy/systemd examples untested; no server exists |
| Hosting on PythonAnywhere | Not implemented | discussed as a possible option only |
| Multi-tenant organizations | Planned (decision pending) | `docs/engineering-assessment.md` H2 |
| Asset-level graph | Planned | assessment M7 |
| Uncertainty / Monte-Carlo mode | Planned | assessment M8 |
| MFA for CodeGuard accounts | Not implemented | — |
| PostgreSQL support | Not implemented | settings are generic; untested |
| Background job queue, REST API, PDF generation | Not implemented | the report document is printed by the browser (`data-print` button) |
| Screen-reader testing | Not implemented | README states it was never done |

---

## 2. Technology stack

**What it is and why.** A deliberately small, conventional stack: everything needed ships with
Python plus three runtime packages.

| Layer | Technology | Version | Role in CodeGuard |
|---|---|---|---|
| Language | Python | ≥ 3.12 (verified 3.12.10) | everything server-side |
| Framework | Django | 5.2.18 | ORM, migrations, templates, auth, sessions, CSRF, admin, management commands |
| Database | SQLite | bundled with Python | one file, WAL mode |
| Charts | Matplotlib (Agg backend) | 3.11.2 | PNG charts rendered in memory |
| Configuration | python-dotenv | 1.2.4 | loads `.env` |
| CSS/JS | Bootstrap + Bootstrap Icons (vendored), one hand-written `app.js`, one `codeguard.css` | not recorded | layout, components, progressive enhancement |
| Fonts | Google Fonts (Instrument Sans, JetBrains Mono, Newsreader) | — | the only third-party request |
| Tests | pytest, pytest-django, pytest-cov, coverage | 9.1.1 / 4.14.0 / 7.1.0 / 7.17.0 | 337 tests |
| Quality | Ruff | 0.17.2 | lint (incl. security rules) and format |
| Supply-chain hygiene | pip-audit | 2.10.1 | dependency vulnerability scan |
| CI | Jenkins (Declarative `Jenkinsfile`), GitHub Actions | — | quality gates; no deployment |
| Optional verification | Node ≥ 22 + axe-core 4.10.2 + Chrome; Python `requests` | — | accessibility and live authorization checks |

Not used: any JavaScript framework or bundler, Celery/Redis, Docker, a REST framework, a WSGI
server package (installed separately at deployment). Details:
[references/dependencies.md](references/dependencies.md).

---

## 3. Directory structure

```
CODEGUARD/
├── codeguard/            project package: settings.py, test_settings.py, urls.py, wsgi.py, asgi.py
├── accounts/             roles, registration, throttling, session epoch, settings pages, preferences
├── audit/                AuditEvent, record_event, audit log, purge_audit_events command
├── threats/              stages, controls, scenarios, rules, forms, seed data, seed command
├── simulation/           domain, engine, propagation, risk, recommendations, serialization,
│                         services, views, charts (Matplotlib), visual (SVG), exports (CSV)
├── remediation/          RemediationItem, plan and detail views, verification
├── core/                 landing, dashboard, analytics, notifications, help, healthz, errors,
│                         CSP + request-ID middleware, theme script, SVG charts, template tags,
│                         backup_db command
├── templates/            base.html, layouts/, components/, partials/, illustrations/, and one
│                         folder per area (core, dashboard, supply_chain, risk, threats,
│                         simulation, reports*, remediation, audit, settings, registration, errors)
├── static/               css/codeguard.css, js/app.js, images/favicon.svg, vendor/ (Bootstrap)
├── tests/                cross-app integration tests and CI-script tests
├── scripts/              ci_local.ps1/.sh, ci_deploy_check.py, ci_dependency_audit.py,
│                         rehearse_jenkinsfile.py
├── tools/                a11y/ (Node browser checks), authz_live.py
├── docs/                 project documents; docs/complete/ is this package
├── .github/              workflows/ci.yml, issue and PR templates
├── Jenkinsfile, manage.py, conftest.py, pytest.ini, pyproject.toml
├── requirements.txt, requirements-dev.txt, .env.example
└── README.md, CONTRIBUTING.md, DESIGN.md, PLAN.md
```

`*` `templates/reports/` exists on disk but is excluded by `.gitignore` (§16). Each app follows
the Django layout (`models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`, `migrations/`,
`tests/`) plus a `services.py` for business rules. Local-only items not described here:
`db.sqlite3`, `.env`, `.venv/`, `backups/`, `reports/`, caches, and a stray clone folder
`codeguard-clean/`.

---

## 4. Backend

**What it is.** A Django monolith with six project apps (see
[ARCHITECTURE.md §2](ARCHITECTURE.md#2-the-apps)).

**Why this shape.** One deployable unit is the simplest thing that works for a single team, and
Django supplies authentication, forms, an ORM, migrations and an admin without extra services.

**How it works.** Requests pass a ten-entry middleware chain (`codeguard/settings.py`
`MIDDLEWARE`), reach function-based views, which call service functions, which use the ORM. The
simulation engine is a separate pure-Python layer that services call with immutable dataclasses.
The dependency rule, quoted from `simulation/domain.py`: "These classes deliberately have no
Django dependency… a simulation cannot accidentally read or write the database."

**How CodeGuard uses it — the main execution path, end to end.**

1. `POST /simulations/new/` → `simulation.views.configure` (decorated `analyst_required`).
2. `SimulationForm` validates ranges (likelihood 0–100, severity/impact 1–5, threshold 1–100)
   and limits the scenario to *active scenarios visible to this user*.
3. `services.run_simulation` builds a `SimulationInput` (`build_input`) from all stages, the
   scenario's rules and the chosen controls, and calls `engine.validate_input` — an invalid
   configuration raises `SimulationConfigError` and **no run is created**.
4. A `SimulationRun` row is created with status `pending` and a version-2 `input_snapshot`.
5. Inside `transaction.atomic()`, `_execute` runs `engine.simulate`, `recommend` and
   `control_contributions`, bulk-creates `SimulationStageResult` and `PropagationEvent` rows,
   stores `result` JSON and headline scores, and sets status `completed`.
6. Any exception rolls back the children and marks the run `failed` with a generic message; an
   audit event is written either way (`simulation_run` or `simulation_failed`).
7. If the user prefers it, the report is shared at once. The browser is redirected to
   `/simulations/<uuid>/`.
8. The result page and its chart PNGs read **only stored data**.

Sequence diagram: [diagrams/simulation-workflow.md](diagrams/simulation-workflow.md).

**Source files.** `simulation/views.py`, `forms.py`, `services.py`, `engine.py`,
`recommendations.py`, `serialization.py`, `models.py`.

**Example.** `threats/services.save_scenario` is the same pattern on the scenario side: one
atomic function that saves the scenario (incrementing `version` on edits, forcing `private` for
non-admins), its rule formset and its control links.

**Limitations.** Synchronous execution in the request (fine at millisecond cost); function views
with inline context building; no API layer.

---

## 5. Frontend

**What it is.** Server-rendered Django templates styled by one design-token stylesheet and
enhanced by one small script.

**Why.** No build step, works without JavaScript for nearly everything, and keeps all logic on
the server where it is tested.

**How it works.** `templates/base.html` loads Google Fonts, vendored Bootstrap CSS/Icons,
`static/css/codeguard.css`, the Bootstrap bundle and `static/js/app.js`, and writes the pre-paint
theme script inline (allowed by its CSP hash). User preferences become `data-*` attributes on
`<html>`, which the CSS token blocks read. `app.js` adds confirmation dialogs, loading states,
print buttons, accessible scroll regions, the theme toggle, chart tooltips, the configuration
stepper and chart re-colouring for the active theme.

**How CodeGuard uses it.** `DESIGN.md` is the design authority; `CLAUDE.md` adds "Never
hardcode colors; use the CSS variables", and `core/tests/test_design.py` enforces it
automatically. The five-stage pipeline diagram is an SVG whose geometry is computed in
`simulation/visual.build_pipeline` and drawn by `templates/components/pipeline.html`.

**Source files.** `templates/`, `static/css/codeguard.css`, `static/js/app.js`, `core/theme.py`,
`core/templatetags/codeguard_tags.py`, `accounts/preferences.py`.

**Limitations.** The vendored Bootstrap version is not recorded; Google Fonts is a third-party
request on every page; browser behaviour of `app.js` is tested only by the optional Node tools.
More: [ARCHITECTURE.md §4](ARCHITECTURE.md#4-frontend).

---

## 6. Database

**What it is.** One SQLite file accessed through the Django ORM: 12 CodeGuard models in 13
tables, plus 10 Django framework tables, created by 15 project migrations.

**Why.** Zero administration for a single-team academic tool.

**How it works.** WAL journal, IMMEDIATE transactions and a 20-second busy timeout let several
worker processes share the file. Integrity rules (ranges, uniqueness, no self-loops, private
scenarios must have an owner, one active remediation item per control and scenario) are database
constraints as well as form rules. History is denormalised so reports outlive scenarios.

**How CodeGuard uses it.** Reference data (stages, controls, system scenarios) is loaded by the
idempotent `seed_codeguard` command rather than by migrations. JSON columns hold snapshots,
results and audit metadata.

**Example.** The data migration `accounts/migrations/0006_retire_neutral_surface.py` moves users
off a retired preference value before narrowing the choices; it was reversed and re-applied on a
scratch database for this documentation.

**Limitations.** One writer at a time, same-host only, no tested PostgreSQL path, and
audit-table immutability is enforced in Python only.

More: [DATABASE_AND_MIGRATIONS.md](DATABASE_AND_MIGRATIONS.md),
[diagrams/erd.md](diagrams/erd.md), [references/models-and-tables.md](references/models-and-tables.md),
[references/migrations.md](references/migrations.md).

---

## 7. Authentication, authorization and security

**What it is.** Django session authentication with three CodeGuard roles (admin, analyst,
viewer) stored in `Profile.role`, server-side role decorators, object-level scoped querysets,
and a hardened HTTP layer.

**Why.** Scenarios and reports can be private; administrators manage shared content and users;
the audit trail must be trustworthy.

**How it works.**

* *Sign-in* uses `ThrottledAuthenticationForm`, which refuses before checking the password when
  a username has 5 failures, or an IP has 20, within 15 minutes, counting audit events.
* *Registration* never lets the user choose a role; `CODEGUARD_REGISTRATION` decides who may
  register at all.
* *Authorization* is checked in every protected view (`login_required`, `analyst_required`,
  `admin_required`, and `can_edit`/`can_delete`); objects are fetched through
  `visible_scenarios`, `accessible_runs` and `items_for`, and a miss is a 404.
* *Sessions* last 8 hours and end at browser close; "sign out other sessions" increments a
  per-user epoch checked by `SessionEpochMiddleware`.
* *Headers*: strict CSP with a script hash, `X-Frame-Options: DENY`, `nosniff`, same-origin
  referrer and opener policies, a restrictive Permissions-Policy, HTTPS/HSTS/secure cookies by
  default when DEBUG is off.

**How CodeGuard uses it.** See the role matrix in [SECURITY.md §3.1](SECURITY.md#31-role-matrix-from-decorators-and-service-checks).
Viewers can read shared content and their own audit events; analysts create private scenarios,
run simulations and manage their remediation plan; admins also manage shared scenarios, users
and the organization page and see every audit event. Admins do **not** get access to other
users' private scenarios or runs (tested).

**Example.** `GET /simulations/<another user's private run>/` → `get_accessible_run` finds
nothing → 404, the same response as for a non-existent ID
(`test_other_user_cannot_open_private_report_chart_or_csv`).

**Honest gaps.** No MFA for CodeGuard accounts; per-IP throttling becomes one shared bucket
behind a reverse proxy because only `REMOTE_ADDR` is trusted; open registration by default with
instance-wide sharing (single-tenant by design); `/admin/` is outside the CSP and the audit
trail; no penetration test. Full list: [SECURITY.md §8](SECURITY.md#8-summary-of-gaps).
Diagram: [diagrams/authentication.md](diagrams/authentication.md).

---

## 8. Threat modelling in CodeGuard

Two different things carry this name; keep them apart.

**8.1 Threat scenarios (the product's subject matter).** A `ThreatScenario` is a hypothetical
attack: an entry stage, base likelihood (0–100), severity and impact (1–5), a propagation
threshold (default 50), narrative fields (business impact, assets, assumptions, preventive and
detective measures), and a set of `PropagationRule` edges with probabilities and rationales.
Scenarios are shared or private, active or archived, versioned on every edit, and the six seeded
system scenarios cannot be deleted. The seeded set covers every stage as an entry point:

| Scenario | Entry | L / S / I | Notable edges |
|---|---|---|---|
| Compromised Developer Account | IDE | 70 / 4 / 4 | forward chain + IDE → CI/CD bypass |
| Compromised Version Control Account | VCS | 60 / 4 / 4 | VCS → IDE reverse |
| Compromised CI/CD Pipeline | CI/CD | 55 / 5 / 5 | CI/CD → VCS reverse, CI/CD → Production bypass |
| Malicious Dependency | Registry | 50 / 4 / 4 | reverse edges to IDE and CI/CD, a CI/CD ↔ Registry cycle |
| Compromised Software Registry | Registry | 45 / 5 / 5 | Registry → CI/CD reverse, CI/CD → Production bypass |
| Production Credential Exposure | Production | 65 / 5 / 5 | only reverse edges (30 %, 35 %) |

Status: **implemented and verified** (`test_every_seeded_scenario_simulates_successfully`).

**8.2 The threat model of the application itself.** `docs/threat-model.md` applies STRIDE to
CodeGuard (assets, actors, trust boundaries, mitigations, residual risks). This package's
[SECURITY.md](SECURITY.md) maps those mitigations to code and tests.

---

## 9. Simulation and risk scoring

**What it is.** A deterministic graph model (`MODEL_VERSION = "1.0"`).

**How it works — the formulas** (complete definitions in
[SIMULATION_AND_RISK_METHODOLOGY.md §2](SIMULATION_AND_RISK_METHODOLOGY.md#2-formulas)):

```
coverage(s)          = 100 × (1 − ∏(1 − εᵢ/100))       per stage, per mode (prevent / mitigate)
effective(u→v)       = p × (1 − P(v)/100)
propagates           ⇔ effective ≥ τ                   (else blocked if p ≥ τ, else below threshold)
L_entry              = L₀ × (1 − P(entry)/100)
λ(v)                 = best successful path product, or strongest failed attempt
raw(λ)               = λ × (severity/5) × (impact/5)
residual_risk(s)     = raw(λ_residual(s)) × (1 − M(s)/100)
overall              = Σ risk(s)·w(s) / Σ w(s)
bands                low < 15 ≤ moderate < 30 ≤ high < 50 ≤ critical
```

The traversal is breadth-first, evaluates every edge at most once (so cycles terminate), and
picks the most likely path with a max-product Dijkstra variant. The inherent pass ignores all
controls; the residual pass applies preventive coverage to edges and to the entry stage, and
mitigating coverage to stage risk.

**Worked example (summary).** "Compromised Developer Account" with MFA, protected branches and
SCA: inherent overall **26.6 (moderate)**, residual overall **3.3 (low)**; only the entry stage
stays compromised; IDE → Version Control is blocked (85 % → 17 %), IDE → CI/CD is below the
threshold (40 %). Step-by-step numbers:
[SIMULATION_AND_RISK_METHODOLOGY.md §3](SIMULATION_AND_RISK_METHODOLOGY.md#3-worked-example).

**Limitations** (also shown on every report's "Inputs and method" tab): fixed threshold, not a
calibrated prediction; illustrative effectiveness values; independent controls; single best path,
not a sum; no telemetry. Further observed limitations (discontinuity at the threshold, scenario-
wide severity) are listed in §7 of the methodology document.

---

## 10. Controls and recommendations

**What it is.** A catalogue of 14 controls (`threats/seed_data.CONTROLS`): 11 preventive, 2
detective (`sca`, `runtime-monitoring`) and 1 recovery (`incident-response`). Each has an
effectiveness parameter, the stages it protects, effort, priority, what it addresses, and since
migration `threats.0003` an `effectiveness_basis` and `limitations` text, so the number is never
presented without its assumption (`test_every_seeded_control_states_its_basis_and_limitations`).

**Why.** Students need to see that controls differ in what they do (prevent vs mitigate), where
they act, and how much they cost, and that a stated number is an assumption.

**How it works.** Preventive controls reduce the probability of entering the stages they protect;
detective and recovery controls reduce the residual risk of a reached stage. Recommendations are
computed by **re-running the engine** with each disabled, relevant candidate added, ranking by the
exact modelled reduction (ties: scenario-applicable first, lower effort, higher priority, name),
and keeping five. Contributions of enabled controls are computed leave-one-out.

**How CodeGuard uses it.** The "Controls and recommendations" tab shows both lists with reasons;
"Add to plan" turns a recommendation into a `RemediationItem` (§11). The dashboard aggregates
recommendations across a user's last ten runs (`core.services.top_recommendations`).

**Example.** In the worked example the top recommendation is dependency pinning (−1.9 points),
because it also protects the entry stage.

**Limitations.** Reductions are model outputs, not expected real-world effects; contributions do
not add up because controls interact.

---

## 11. Remediation

**What it is.** A per-user plan of controls the user committed to adopt (`remediation` app).

**How it works.** `remediation.services.track` accepts only controls that appear in the run's
stored recommendations, stores the baseline risk and expected reduction, and refuses duplicates
(service check plus a partial unique index). Items move between open, in progress, done and risk
accepted; `closed_at` is set and cleared accordingly; every change is audited. *Verification* is
derived, not stored: the owner's latest later completed run of the same scenario with the control
enabled (`services.verification`). The plan can be filtered by status and sorted by due date,
modelled impact or recency; overdue and unscheduled counts are shown.

**Status.** Implemented and verified (`remediation/tests/test_remediation.py`, 11 tests). Viewers
cannot create or edit items.

---

## 12. Reporting, charts and analytics

| Output | Where | Technology | Status |
|---|---|---|---|
| Result tabs: summary (with affected assets), stage analysis, propagation paths, controls and recommendations, inputs and method | `/simulations/<id>/<section>/` | templates + stored rows | verified |
| Charts: overall inherent vs residual, risk by stage, outcomes by type | `/simulations/<id>/chart/<kind>.png` | Matplotlib, in memory | verified |
| Before/after comparison and its chart | `/simulations/compare/?a=&b=` | Matplotlib | verified |
| Reports archive and printable assessment document | `/reports/`, `/reports/<id>/` | templates | verified (tracked since commit `eef6716`) |
| CSV export of a run and of one's history | `export.csv` routes | `csv` + `safe_cell` | verified |
| Overview: run totals, averages, band distribution, stage strip, remediation summary, recommended controls | `/overview/` (+ PNG) | ORM aggregates, SVG bars, Matplotlib | verified |
| Supply-chain map and stage pages | `/supply-chain/` | `core/analytics.py` | verified |
| Risk analysis: trend of the 24 latest runs, exposure by stage, control effects | `/risk/` | `core/svgcharts.py` | verified |

Charts take their colours from the page's CSS tokens via `?palette=`, falling back to the light
palette, and every chart has a text or table alternative. Charts are only served for runs the
user may access, with `Cache-Control: private`.

---

## 13. Audit trail

**What it is.** `audit.AuditEvent`, an append-only record of 25 kinds of actions.

**Why.** Accountability for security-relevant actions, evidence for throttling, and a source for
the security page and notifications.

**How it works.** `audit.services.record_event(actor, action, target, request, **metadata)`
stores the actor and username, the object type/id/repr, sanitised metadata (keys containing
password, secret, token, session, csrf, key or credential are dropped; values truncated) and
`REMOTE_ADDR`. Updates and deletes raise at the model and queryset level; deleting a user keeps
their events. `purge_audit_events --days N` (minimum 30) is the only way to remove history, and
it records itself.

**How CodeGuard uses it.** `/audit/` (timeline or table, filters) shows administrators every
event and others their own. `accounts/throttling.py` counts `login_failed` events;
`/settings/security/` lists recent account events; `core/notifications.py` derives
"shared report" and "security" notifications from events.

**Limitations.** No database triggers, so raw SQL could still alter rows; Django admin actions
are not recorded here; IP addresses are the proxy's behind a proxy.

---

## 14. Testing and quality assurance

**Status on 2026-11-10.** 337 tests exist and **all 337 passed** in the working tree; coverage
96 % overall and 99 % on the four core engine modules (gate: 85 %); Ruff clean; no missing
migrations; `check --deploy` has no errors. A fresh clone of `8f5d092` failed 9 tests because
the Reports templates were git-ignored; after the fix in commit `eef6716` a fresh clone passes all 337. Browser accessibility checks, the live authorization
matrix and the Jenkins rehearsal were not re-run (their earlier results are recorded in the
README). `pip-audit` was re-run: no known vulnerabilities. GitHub Actions passed on its run #7
(commit `8ca8b36`).

Strategy: pure engine unit tests, service/view tests through Django's test client, integration
tests, tests that enforce the design system on CSS and templates, Python-level accessibility
tests and optional browser tools. Details and gaps:
[TESTING_AND_QUALITY_ASSURANCE.md](TESTING_AND_QUALITY_ASSURANCE.md),
[references/tests.md](references/tests.md).

---

## 15. Git, GitHub, Jenkins and CI/CD

* **Git/GitHub.** 10 commits on `main` (2026-10-27 → 2026-11-10), one author
  (`bsclmr134322-collab`), remote `github.com/bsclmr111626/software-engineering-project`.
  Contribution guide, issue and PR templates exist.
* **Jenkins.** `Jenkinsfile` defines seven stages: checkout, environment setup, static checks,
  database preparation (migration check, migrate, seed twice), tests with JUnit and coverage,
  core coverage gate, security checks (deploy check and pip-audit with SUCCESS/UNSTABLE/FAILURE
  mapping), then archiving and cleanup. **It is configured but has never been executed on a
  Jenkins server.** `scripts/rehearse_jenkinsfile.py` extracts and runs its commands on a fresh
  clone ("commands only; not a Jenkins execution"); the README records SUCCESS on 2026-10-26.
  Before commit `eef6716` the rehearsal would have failed in the test stage (§16, gap 1).
* **GitHub Actions.** `.github/workflows/ci.yml` mirrors the gates on every push to `main` and
  every pull request. Runs #1–#6 failed; run #7 on commit `8ca8b36` (2026-11-10) **passed**
  every gate in 1 min 5 s. The two causes of the earlier failures were the git-ignored Reports
  templates (fixed in `eef6716`) and Ruff's format check rewriting Python code quoted in the new
  Markdown docs (fixed in `8ca8b36` by excluding `*.md` from `ruff format`).
* **CD.** None: no pipeline builds a release or deploys.

Diagram: [diagrams/ci-cd.md](diagrams/ci-cd.md); details:
[DEVELOPMENT_AND_DEPLOYMENT.md §3–4](DEVELOPMENT_AND_DEPLOYMENT.md#3-git-and-github).

---

## 16. Configuration and environment variables

All settings that vary between environments are environment variables, optionally loaded from
`.env` (copied from `.env.example`). The key ones: `DJANGO_DEBUG`, `DJANGO_SECRET_KEY` (required
when DEBUG is off), `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_DB_PATH`,
`CODEGUARD_REGISTRATION` (+ `_DOMAINS`), `CODEGUARD_DEFAULT_ROLE`, the three `CODEGUARD_LOGIN_*`
throttling values, the email variables, the transport-security switches and the two logging
variables. Invalid enumerations stop start-up with `ImproperlyConfigured`.
`DJANGO_HSTS_INCLUDE_SUBDOMAINS` is read by settings but missing from `.env.example`. Complete
table: [references/environment-variables.md](references/environment-variables.md).

### Known gaps found while documenting

1. **Reports templates were not version-controlled — fixed in commit `eef6716`.** The `.gitignore`
   rule `reports/`, meant for CI artefacts, also matched `templates/reports/`, so `list.html` and
   `document.html` were never committed: a clone of `8f5d092` returned 500 on `/reports/` and
   failed 9 tests. The rule is now `/reports/` and both templates are committed; a fresh clone of
   `eef6716` passes all 337 tests. Not yet pushed at the time of writing.
2. **Per-IP sign-in throttling behind a proxy** counts all users as one IP.
3. **`requests` is unpinned** although `tools/authz_live.py` imports it.
4. **`DJANGO_HSTS_INCLUDE_SUBDOMAINS` is undocumented** in `.env.example`.
5. **A route-ordering edge case:** a scenario whose slug is `controls` could never be opened,
   because `threats/controls/` is matched first and `unique_slug` does not reserve it.
6. **Comment drift:** `core/middleware.py` says the Google Fonts allowance is for "Source Serif
   4", but `templates/base.html` loads Instrument Sans, JetBrains Mono and Newsreader.

---

## 17. Installation and deployment

* **Local installation**: the README Quick start (clone, venv, `pip install -r requirements.txt`,
  copy `.env.example`, `migrate`, `seed_codeguard --demo-users`, `runserver`). On this machine,
  call `.venv\Scripts\python.exe` because Python is not on `PATH`.
* **Production**: `docs/deployment.md` describes one Linux host with a WSGI server (gunicorn or
  waitress, installed separately), a TLS reverse proxy serving `collectstatic` output, SQLite on
  local disk, health checks, backups, retention and upgrades. The application-side parts are
  tested; the systemd and nginx snippets are examples that were never run. No production or
  staging server exists.
* **Hosting options**: a self-managed Linux VM (the documented path); PythonAnywhere's free tier
  was discussed as a possible option and **has not been set up or tried**; there is no
  Dockerfile.

Details and troubleshooting:
[DEVELOPMENT_AND_DEPLOYMENT.md](DEVELOPMENT_AND_DEPLOYMENT.md).

---

## 18. Performance

Observed from the code; nothing was benchmarked for this documentation.

* A simulation costs 1 + (number of recommendation candidates) + (number of enabled controls)
  engine runs over a 5-node graph — milliseconds — so synchronous execution is acceptable
  (assessment L1).
* Pages use `select_related`/`prefetch_related`; user preferences are cached per request.
* Dashboard and analytics recompute SQL aggregates over all accessible runs on every request;
  there is no cache.
* The remediation plan has an N+1 pattern (`verification()` per item, up to 50 runs each).
* SQLite allows one writer at a time; the README's 200-run concurrency experiment
  (2026-10-26) is the only load evidence.

---

## 19. Maintainability

Strengths: a pure, well-tested engine; one formula per function with docstrings; enumerations for
every state; constraints in both forms and schema; versioned snapshots; consistent service-layer
access checks; Ruff with security and Django rules; design rules enforced by tests; CI scripts
written in Python so they can be unit-tested. Weak spots: long settings views, inline context
building in views, vendored assets without versions, and version-control hygiene (the Reports templates were ignored
templates). The engine's generic `Stage`/`Edge` model is the intended extension point for an
asset graph (assessment M7).

---

## 20. Troubleshooting (most common)

| Symptom | Fix |
|---|---|
| `DJANGO_SECRET_KEY must be set…` | create `.env` from `.env.example` |
| `no such table` | `python manage.py migrate` |
| No scenarios | `python manage.py seed_codeguard` |
| 500 / `TemplateDoesNotExist: reports/list.html` | a checkout older than `eef6716` lacks the Reports templates (§16) |
| "Too many failed sign-in attempts" | wait 15 minutes or adjust `CODEGUARD_LOGIN_*` |
| No styles in production | `collectstatic` and serve `/static/` from the proxy |
| `python` not found on this PC | use `.venv\Scripts\python.exe` |

Full table: [DEVELOPMENT_AND_DEPLOYMENT.md §7](DEVELOPMENT_AND_DEPLOYMENT.md#7-troubleshooting).

---

## 21. Limitations and future work

**Model.** Deterministic single-point estimates; illustrative parameters; independent controls;
best path only; a hard threshold; scenario-wide severity and impact; a fixed five-stage model.
Future work recorded by the project: an uncertainty (Monte-Carlo) mode (M8) and an optional
asset layer with trust relationships (M7).

**Product and platform.** Single-tenant sharing (organizations need a product decision, H2);
no MFA for CodeGuard accounts; no API; no background jobs; SQLite only.

**Verification.** Jenkins never executed (GitHub Actions does pass, since run #7); no real deployment; no
screen-reader test; no penetration test; browser and authorization checks last run 2026-10-26/28.

**Immediate fixes suggested by this documentation pass**: the Reports templates and ignore rule
were fixed in commit `eef6716`; still open: add a trusted-proxy option for `client_ip`; pin `requests`
in a tools requirements file; add `DJANGO_HSTS_INCLUDE_SUBDOMAINS` to `.env.example`; reserve the
`controls` slug; correct the font comment in `core/middleware.py`.

---

## 22. Glossary and learning guide

Terms: [GLOSSARY.md](GLOSSARY.md). A ten-stage study path from "run it" to "explain it", with
exercises against the real code: [LEARNING_GUIDE.md](LEARNING_GUIDE.md).

---

## Appendix — How this documentation was verified

* Every file path, class and function named here was checked against the repository (see the
  final verification notes in the hand-over report).
* Formulas were copied from `simulation/risk.py`, `propagation.py` and `engine.py`; the worked
  example was computed by the real engine on a seeded scratch database and recomputed by hand.
* Test counts come from `pytest --collect-only`; results from runs on 2026-11-10.
* Table names come from a database created from scratch with `migrate`.
* The local `.env` file was not read. No application code was changed.
