# Testing and quality assurance

This document separates three things that are easy to blur: **tests that exist**, **tests that
were run for this documentation (2026-11-10)**, and **checks that were run earlier and only
recorded** in the README or `docs/test-plan.md`. Inventory: [tests](references/tests.md).

## 1. What was actually run on 2026-11-10

| Check | Command | Result |
|---|---|---|
| Full suite, working tree | `.venv\Scripts\python.exe -m pytest` | **337 passed** (36 s) |
| Coverage | `pytest --cov` | **96 %** total (branch coverage, `pyproject.toml [tool.coverage]`) |
| Core gate | `coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=85` | **99 %**, passed |
| Full suite on a fresh `git clone` of `8f5d092` | same interpreter | **9 failed, 328 passed** — `templates/reports/*.html` git-ignored |
| Full suite on a fresh `git clone` of `eef6716` (the fix) | same interpreter | **337 passed** |
| Lint and format | `ruff check .`; `ruff format --check .` | clean (Markdown excluded from formatting since `8ca8b36`) |
| Dependency audit | `python scripts/ci_dependency_audit.py` | No known vulnerabilities, exit 0 |
| GitHub Actions | push of `8ca8b36` | **run #7 passed**, every gate, 1 min 5 s |
| Migrations consistent | `manage.py makemigrations --check --dry-run` | No changes detected |
| Migrations from scratch | `migrate` on an empty scratch DB, then `seed_codeguard` | all applied; 5 stages, 14 controls, 6 scenarios |
| Reversible data migration | `migrate accounts 0005`, then `migrate accounts` | unapplied and re-applied `0006` |
| Deployment check | `python scripts/ci_deploy_check.py` | 0 errors, 3 warnings (`codeguard.W001`, `security.W005`, `security.W021`) |
| Engine worked example | engine called on seeded data | matches the hand calculation in `SIMULATION_AND_RISK_METHODOLOGY.md` |

**Not run** on 2026-11-10: `scripts/rehearse_jenkinsfile.py`, the
Node/Chrome checks in `tools/a11y/`, `tools/authz_live.py` (needs a running server and the
journey output), and any Jenkins run.

## 2. Earlier results that are recorded but were not repeated

From the README "Last verified results" table (2026-10-26/28): 332 tests passed at that time;
`pip-audit` reported no known vulnerabilities; the Jenkinsfile rehearsal returned SUCCESS; a
concurrency test (4 processes × 50 runs) completed 200/200; axe-core reported 0 violations on 47
pages in both themes at 1280 px and 390 px; a keyboard journey passed 14/14 checks in real
Chrome; the remediation workflow passed 8/8; the live authorization matrix passed. These are
**claims recorded by the project**; this documentation did not reproduce them. The test count
has since grown from 332 to 337.

## 3. Test strategy (as implemented)

**Pyramid.**

1. **Pure unit tests** of the formulas and the engine (85 tests in `test_risk.py` and
   `test_engine.py`) use `simulation/tests/factories.py` and never touch the database. They pin
   every formula with exact expected values, the boundaries of every range, threshold
   inclusivity, float-noise handling, cycles, bypass and reverse edges, most-likely-path
   selection, determinism (edge order does not matter) and validation errors.
2. **Service and view tests** with pytest-django's `client`: persistence and rollback,
   snapshots, access control (IDOR), CSV content and injection, charts and palettes, role
   checks, form validation, audit events.
3. **Integration tests** (`tests/test_integration.py`): a full analyst journey, every main page
   rendering for an analyst, every seeded scenario simulating successfully, migrations
   consistent with models, `manage.py check` clean.
4. **Rule tests on non-Python assets** (`core/tests/test_design.py`): parse
   `static/css/codeguard.css`, templates and `app.js` to enforce `DESIGN.md` (colours only in
   token blocks, identical token sets for light and dark, no theme branching, chart token order
   matches `PALETTE_TOKENS`).
5. **Accessibility tests in Python** (`core/tests/test_accessibility.py`): errors linked to
   inputs, navigation state, accessible names on the report page.
6. **Optional browser tools** (not part of pytest): `tools/a11y/` (axe-core, keyboard, reflow,
   journey) and `tools/authz_live.py`.

**Isolation.** `pytest.ini` uses `codeguard.test_settings`, which forces `DJANGO_DEBUG=false`
(so production-mode code paths are tested), a fixed test secret, no HTTPS redirect, the MD5
hasher for speed and the in-memory email backend. pytest-django creates a temporary database
per session. `filterwarnings = error::RuntimeWarning` turns runtime warnings (for example naive
datetimes) into failures, and `--strict-markers` rejects typos in markers.

**Fixtures.** Users are created through `conftest._make_user` with explicit roles; `seeded`
loads the real seed data so tests use the same scenarios users see.

## 4. Static quality gates

| Gate | Configuration | Where it runs |
|---|---|---|
| Ruff lint | `pyproject.toml`: rule sets `E, F, W, I, B, UP, DJ, S`; ignores `E501`, `S101`, `S311`; migrations excluded | `ci.yml`, `Jenkinsfile`, `scripts/ci_local.*` |
| Ruff format | line length 120 | same |
| Django system checks | `manage.py check`; `check --deploy --fail-level ERROR` via `ci_deploy_check.py` | same |
| Migration drift | `makemigrations --check --dry-run` | same, plus an integration test |
| Core coverage gate | ≥ 85 % on the four engine modules | same |
| Dependency audit | `pip-audit -r requirements.txt` with exit codes 0/1/2 | same (GitHub Actions treats 2 as failure; Jenkins as UNSTABLE) |

## 5. Requirement-to-test traceability

`docs/test-plan.md` maps requirements (in `docs/requirements.md`) to test names and lists
boundary values covered. For this documentation every `test_…` name cited there (94 distinct
names) was compared with the collected test list: all exist. Whether each test really proves
its requirement was not re-judged.

## 6. What the tests do not cover

* **Clean checkouts in CI.** Until commit `eef6716` the suite passed only in the developer's working
  tree (the Reports templates were git-ignored). A fresh clone now passes locally and GitHub
  Actions passed on run #7; no Jenkins run is on record.
* **Real HTTPS, a real WSGI server and a reverse proxy** beyond the PythonAnywhere instance
  (checked by hand on 2026-11-12, not by an automated test); the nginx and systemd examples in
  `docs/deployment.md` are still marked "not tested here".
* **Concurrency** beyond the one recorded 200-run experiment.
* **Browser behaviour** of `app.js` (tooltips, stepper, theme toggle) except through the
  optional Node tools.
* **Screen readers** (never tested; README says so).
* **Security testing** beyond functional tests of the controls: no fuzzing, no scanner, no
  penetration test.
* **Model validity.** The tests prove the engine implements its formulas; nothing can prove the
  formulas describe real attacks (see the methodology limitations).

## 7. How to run

```bash
.venv\Scripts\python.exe -m pytest                       # Windows, this machine
pytest -k engine                                          # a subset by name
pytest simulation/tests/test_risk.py::TestRoundingAndClassification -q
pytest --cov --cov-report=html                            # report in htmlcov/
powershell -ExecutionPolicy Bypass -File scripts\ci_local.ps1   # every gate, Windows
./scripts/ci_local.sh                                     # every gate, Linux/macOS
python scripts/rehearse_jenkinsfile.py                    # Jenkinsfile commands on a fresh clone
```

`scripts/rehearse_jenkinsfile.py` clones HEAD (`checkout()` uses `git clone`), so it tests what
is committed, not the working tree; it was not re-run after commit `eef6716`.
