# Reference: automated tests

Collected with `pytest --collect-only` on 2026-11-10: **337 tests in 15 files**. Parametrised
tests count once per parameter.

## Results actually obtained on 2026-11-10 (Windows 11, Python 3.12.10)

| Run | Command | Result |
|---|---|---|
| Working tree | `.venv\Scripts\python.exe -m pytest` | **337 passed** in 36 s |
| Working tree with coverage | `pytest --cov` | 337 passed; **96 %** total branch-aware coverage |
| Core coverage gate | `coverage report --include=simulation/engine.py,…risk.py,…propagation.py,…recommendations.py --fail-under=85` | **99 %**, exit 0 (engine 99 %, propagation 100 %, recommendations 98 %, risk 97 %) |
| Fresh `git clone` of HEAD `8f5d092`, same interpreter | `pytest` | **9 failed, 328 passed**: `TemplateDoesNotExist: reports/list.html` / `reports/document.html` (the templates were git-ignored; see the master document, "Known gaps") |
| Fresh `git clone` of `eef6716` (the fix) | `pytest` | **337 passed** |
| Lint / format | `ruff check .`, `ruff format --check .` | clean (Markdown excluded from formatting since `8ca8b36`) |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Deployment check | `python scripts/ci_deploy_check.py` | 0 errors; 3 warnings: `codeguard.W001` (open registration), `security.W005`, `security.W021` (HSTS subdomains/preload) |
| Dependency audit | `python scripts/ci_dependency_audit.py` | No known vulnerabilities, exit 0 |
| GitHub Actions CI | push of `8ca8b36` | **run #7 passed** (all gates, 1 min 5 s); runs #1–#6 failed |

Not run on 2026-11-10: the Jenkins rehearsal, the Node browser
tools and `tools/authz_live.py` (need a running server). Their last recorded results are in the
README's "Last verified results" table, dated 2026-10-26/28.

## Inventory by file

| File | Tests | What it covers |
|---|---|---|
| `simulation/tests/test_risk.py` | 44 | Formula unit tests: `raw_risk`, `residual_risk`, `combined_effectiveness`, `round_score` (half-up, clamp), `classify` band edges (14.9/15/29.9/30/49.9/50), `weighted_overall`, `meets_threshold` float noise, input validation |
| `simulation/tests/test_engine.py` | 41 | `TestPropagation` (chain, threshold inclusive, zero/100 % edges, bypass, reverse, cycles, most-likely path, weighted overall), `TestControls` (preventive blocks, mitigating reduces risk but not propagation, entry-stage prevention, bounded combination), `TestDeterminism`, `TestValidation` |
| `simulation/tests/test_recommendations.py` | 6 | Exact modeled reduction, ranking, limit, exclusion of enabled/useless controls, leave-one-out contributions, JSON-safe serialisation |
| `simulation/tests/test_services_and_views.py` | 32 | `TestRunPersistence` (children saved, failure rollback, snapshot reproduces result, stability after scenario edit/deletion, invalid config creates no run), `TestConfigureView` (prefill, rerun, range checks, viewer denied, no access to others' private scenarios), `TestReportAccess` (IDOR on report/chart/CSV, sharing, palette, CSV formula injection, history scope), `TestComparison` |
| `threats/tests/test_scenarios.py` | 37 | CRUD, versioning, graph validation, database constraints, permissions (analyst vs admin vs viewer, system scenarios), control library, seed command idempotency and demo-user guard |
| `accounts/tests/test_auth.py` | 30 | Login/logout, registration (role never admin), registration policy (`open/domain/closed`, `W001`), throttling (6 tests), role changes |
| `accounts/tests/test_settings.py` | 32 | Every settings page renders, each preference saved and applied, surface migration rules, email change needs password, session revocation, data export scope, admin-only pages |
| `audit/tests/test_audit.py` | 11 | Safe context, sensitive-key stripping, truncation, append-only (save, bulk update/delete), survival after user deletion, retention purge, visibility (admin vs own) |
| `remediation/tests/test_remediation.py` | 11 | Track only recommended controls, no duplicates (service and DB constraint), privacy, status transitions and `closed_at`, verification by a later run |
| `core/tests/test_core.py` | 27 | Security headers and CSP, theme script hash, health check, request IDs, JSON logs, WAL/IMMEDIATE SQLite, error pages without debug details, dashboard metrics from the DB, backup command |
| `core/tests/test_areas.py` | 15 | Supply-chain map, stage page, risk analysis, notifications, result sections and report document, SVG chart geometry |
| `core/tests/test_design.py` | 10 | `DESIGN.md` rules enforced on CSS/templates/JS: colours only in token blocks, same tokens in both themes, chart palette order matches the server |
| `core/tests/test_accessibility.py` | 7 | Error messages linked to inputs, active navigation marked, report page names its diagram/tables/charts |
| `tests/test_integration.py` | 30 | Full analyst journey, every main page renders (parametrised), every seeded scenario simulates, `makemigrations --check`, `manage.py check` |
| `tests/test_ci_scripts.py` | 4 | `ci_dependency_audit.classify` exit codes; the Jenkinsfile uses scripts and no sandbox-restricted calls |

## Fixtures

`conftest.py`: `seeded` (runs `seed_codeguard`), `analyst` (alice), `other_analyst` (bob),
`viewer` (victor), `admin_user` (ada), and logged-in clients `analyst_client`, `viewer_client`,
`admin_client`. `simulation/tests/factories.py` builds engine inputs without the database
(`make_input`, `chain_edges`, a five-stage `STAGES` tuple with weights 1, 2, 2, 2, 3).

## Configuration

`pytest.ini`: `DJANGO_SETTINGS_MODULE = codeguard.test_settings`, `testpaths` = the six apps plus
`tests`, `addopts = -ra --strict-markers`, `filterwarnings = error::RuntimeWarning`.
`codeguard/test_settings.py`: MD5 password hasher (speed), in-memory email backend, test hosts.
`pyproject.toml [tool.coverage]`: branch coverage over the six apps, omitting migrations,
tests, `admin.py` and `apps.py`.
