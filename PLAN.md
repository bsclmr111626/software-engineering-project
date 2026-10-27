# CodeGuard — Implementation Plan and Progress

CodeGuard is an educational Django application that simulates how a compromise propagates through a five-stage software supply chain (IDE → Version Control → CI/CD → Registry → Production), scores the risk with transparent formulas, and shows how security controls change the outcome.

## Architecture decisions

| Decision | Choice | Reason |
|---|---|---|
| Architecture | Django monolith, 5 apps (`accounts`, `threats`, `simulation`, `audit`, `core`) | Small team, single deployable, no API consumers; easier to explain and test. |
| Simulation engine | Pure Python (`simulation/engine.py`, `risk.py`, `propagation.py`, `recommendations.py`) with no Django imports | Unit-testable in milliseconds; cannot read/write the DB by accident. |
| Propagation decision | Deterministic threshold (`effective probability ≥ threshold`) | Reproducible and explainable; documented as a simplification, not a prediction. |
| Overall risk | Criticality-weighted average of stage risks | The maximum is dominated by the entry stage and would hide downstream controls; peak stage risk is still reported. |
| Control combination | `1 − ∏(1 − eᵢ)` | Bounded ≤ 100 %; independence assumption documented. |
| History | Run stores a versioned JSON snapshot of inputs + full result; children rows denormalised | Reports never change when scenarios are edited or deleted (`scenario` FK is `SET_NULL`). |
| Charts | Matplotlib OO API + Agg, rendered in memory per request behind access-controlled views | No files on disk, no path exposure, no global pyplot state. |
| Frontend | Django templates, Bootstrap 5.3.3 + Bootstrap Icons **vendored** in `static/vendor` | Works offline, allows a strict CSP (`script-src 'self'`, no inline scripts/styles). |
| Database | SQLite | Spec requirement; no concurrency needs that justify PostgreSQL. |
| Roles | `Profile.role` (admin / analyst / viewer), checked server-side in decorators/services | Simple, testable; self-registration can never grant admin. |

## Assumptions recorded

- Self-registered users get the **Analyst** role by default (configurable to Viewer via `CODEGUARD_DEFAULT_ROLE`) so a student can register and immediately run simulations. Administrators are created with `createsuperuser` or promoted by another administrator.
- "Private" scenarios and reports are visible only to their owner — including to administrators in the UI (administrators oversee activity through the audit log). Reports can be explicitly *shared* read-only with all users, which is how viewers see results.
- Seed data is the source of truth for stages and the control catalog (updated on every seed). System scenarios are created once and then left alone so administrator edits survive re-seeding; `--reset-scenarios` restores them.
- Password reset uses Django's console email backend locally (the email is printed in the server terminal).
- Python 3.12.10 and Git were not installed on the development machine and were installed with `winget` (user scope).

## Milestones (Lean: small, demonstrable increments)

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 1 | Django foundation, settings from env, auth (register/login/logout/reset), roles | ✅ Done | `accounts/tests/test_auth.py` |
| 2 | Domain models, migrations, constraints, idempotent seed, threat library CRUD | ✅ Done | `threats/tests/test_scenarios.py` |
| 3 | Simulation engine, risk formulas, recommendations + unit tests | ✅ Done | `simulation/tests/test_engine.py`, `test_risk.py`, `test_recommendations.py` (99 % core coverage) |
| 4 | Dashboard, pipeline SVG, Matplotlib charts, history | ✅ Done | `core/tests/test_core.py`, screenshots reviewed |
| 5 | Before/after comparison, snapshots, audit trail, CSV export, sharing | ✅ Done | `simulation/tests/test_services_and_views.py`, `audit/tests` |
| 6 | Security hardening (CSP, headers, IDOR, CSRF, deploy check), integration tests, CI | ✅ Done | `tests/test_integration.py`, `Jenkinsfile`, `manage.py check --deploy` |
| 7 | Documentation and final acceptance verification | ✅ Done | `README.md`, `docs/`, final report |
| 8 | Independent re-verification, Jenkins validation, accessibility audit (2026-10-26) | ✅ Done (Jenkins *server* run not possible) | See "Verification round 2" below |

## Progress checklist

- [x] Inspect environment; install Python 3.12 / Git; create `.venv`
- [x] Project skeleton, settings, `.env.example`, `.gitignore`
- [x] Accounts: registration (no role field), login, logout (POST), password change/reset, roles, admin role management
- [x] Models + migrations with check/unique constraints and indexes
- [x] `seed_codeguard` (idempotent; `--reset-scenarios`; `--demo-users` DEBUG-only)
- [x] Threat library: search/filter/paginate, detail, create/edit with rule formset + graph validation, archive/restore, delete (confirm), clone
- [x] Simulation engine + risk + propagation + recommendations + serialization
- [x] Run lifecycle PENDING → COMPLETED / FAILED with atomic writes
- [x] Results page: pipeline SVG, legend, stage cards, explanations, events, recommendations, control contributions, limitations
- [x] Matplotlib charts (overall, by stage, outcomes, before/after, dashboard distribution)
- [x] History, compare, CSV export (formula-injection safe), report sharing
- [x] Audit log (append-only, sanitised metadata, role-scoped view)
- [x] Dashboard with real metrics and empty states
- [x] Methodology/help page with disclaimer
- [x] Error pages 400/403/404/500 + CSRF failure page
- [x] Security headers + strict CSP; `check --deploy` reviewed
- [x] 222 automated tests; coverage 96 % overall, 99 % core
- [x] Ruff lint + format clean
- [x] Jenkinsfile, GitHub Actions workflow, local CI scripts
- [x] README, CONTRIBUTING, docs (requirements, architecture, threat model, data dictionary, test plan, user guide)

## Verification round 2 (2026-10-26)

### Re-verification of the earlier checklist

- I reran every gate myself and reproduced the reported figures: 210 tests passing, 96%/99% coverage, Ruff, checks and `pip-audit` clean.
- Test isolation is confirmed: `db.sqlite3` row counts were identical before and after the full suite.

### Jenkins

Jenkins and Java are **not installed**; Docker is installed but was deliberately not used to install Jenkins. The Jenkinsfile was validated as far as possible without a server, and two real defects were fixed:

1. **Sandbox approval.** `UUID.randomUUID()` would need Groovy-sandbox script approval, so the deployment check moved to `scripts/ci_deploy_check.py`.
2. **Fragile `pip-audit` handling.** The JSON was matched as text, so a real vulnerability could be misreported as a network error. Separately, with no network `pip-audit` retried past the pipeline timeout. This moved to `scripts/ci_dependency_audit.py`, which uses exit codes 0/1/2 and a 180-second cap; its offline path was tested for real (exit 2 after 180 s).

The CI database is now excluded from archived artifacts. `scripts/rehearse_jenkinsfile.py` executed every stage command, parsed from the Jenkinsfile itself, on a clean checkout with a fresh venv: **SUCCESS**.

### Accessibility

I audited with axe-core 4.10.2 in headless Chrome at 1280px and 390px, plus keyboard and focus checks, reflow checks, the accessibility tree, and five error states. Issues found and fixed:

| Issue | Fix |
|---|---|
| Primary button contrast 3.7:1 on 19 pages | Darkened to 5.4:1 |
| Phone zoom-out on 2 pages: hidden table labels escaped the scroll wrapper | `position: relative` on the wrapper |
| Phantom 1px scroll regions: Chrome ignores `position: absolute` on `<caption>` | Tables named with `aria-label` instead |
| Wide tables and the diagram not keyboard-reachable | Focusable, named regions when they scroll |
| Form errors not announced: `aria-describedby` pointed to IDs that didn't exist | Error and help-text elements rendered with matching IDs |
| Auto-submitting selects (WCAG 3.2.2) | Removed |
| Diagram name repeated its full description | Short name plus separate description |
| Unnamed main navigation; `aria-current` on only two links | Navigation named; `aria-current` on every active link |
| Decorative symbols read aloud | Hidden from assistive technology |
| Nested live regions | Errors use `role=alert`, other messages `role=status` |
| Chart text alternatives lacked counts | Exact numbers added |

**Final result: 0 axe violations on 24 pages at both widths, 0 in 5 error states, visible focus on every tab stop, and no reflow overflow.** Not done: testing with a real screen reader.

### Journey and authorization

- **Journey:** a browser-driven run in real Chrome, with keyboard-only key steps, passed 14/14 checks.
- **Authorization:** a live matrix covering a second analyst, a viewer and anonymous access passed 43/43, with the database unchanged.
- **Bug fixed:** a forged or unavailable scenario on the simulation form was rejected *silently*. No run was created, but the error wasn't shown. A visible error and a regression test were added.
- **Confirmed safe:** viewer role-denials (403) are identical for real and non-existent slugs, so they reveal nothing; a test now covers this.

## Paper-theme redesign (2026-10-26)

The UI moved to the light theme in DESIGN.md: tokens in `static/css/codeguard.css`, charts recoloured by risk class, `core/tests/test_design.py` added to enforce the rules. A dark theme followed (`[data-theme="dark"]` token block, OS-following toggle, pre-paint inline script allowed by CSP hash, charts redrawn from the live tokens). **Dark mode (2026-10-26):** in the dark theme the only failing pair is white on the dark `--accent` (3.58:1, the primary button); every badge, table, form and the audit log pass. Audit both themes with `npm run audit` and `CODEGUARD_THEME=dark npm run audit` (report: `audit-report-dark.json`). **Open after the paper-theme redesign (2026-10-26):** the DESIGN.md palette fails WCAG AA text contrast in four pairs (white on `--accent` 4.38:1; `--sev-low`, `--sev-med`, `--sev-high` on their tints 4.30, 3.59 and 4.27:1), so axe now reports `color-contrast` on 20 of 22 audited pages. All other checks still pass.

## Engineering review round (2026-10-26)

A product-quality review is recorded in [docs/engineering-assessment.md](docs/engineering-assessment.md). Fixed in this round, each with automated tests:

- Sign-in throttling per username and per IP (H1).
- Registration policy `open` / `domain` / `closed` with a deployment check (H2, single-tenant model).
- Audit log protected against bulk update/delete; retention command (H3).
- Health endpoint, request IDs, optional JSON logs (M1).
- SQLite WAL + immediate transactions + busy timeout. Measured: 200/200 concurrent runs completed, versus 44/200 with Django defaults (M2).
- Online, integrity-checked backups with rotation; restore and retention procedures (M3).
- Remediation plan with verification by re-run (M4).
- Control effectiveness basis and limitations, recorded in run snapshots (M5).
- Deployment guide and SMTP configuration from the environment (M6).

Still open: the palette contrast decision (H4), organizations if multi-team hosting becomes a requirement, the asset graph (M7) and a Monte-Carlo mode (M8).

## Acceptance checklist (verified status)

| Criterion | Status | Evidence |
|---|---|---|
| Register / login / logout; protected pages | Passed | `test_auth.py`; browser journey |
| Roles enforced server-side | Passed | role tests; live matrix (viewer 403s) |
| Private scenarios and reports isolated | Passed | IDOR tests; live matrix 43/43, DB unchanged |
| ≥ 6 seeded scenarios; seed idempotent | Passed | `test_scenarios.py`; seeded twice in the rehearsal |
| Configure and run simulations; documented propagation and formulas | Passed | engine tests (hand-calculated); journey |
| Controls change outcomes; explanations and recommendations | Passed | journey: 26.6 → 3.8, VCS blocked |
| Results saved; history stable after scenario edits | Passed | snapshot tests; journey reopen check |
| Dashboard real data; Matplotlib charts from results | Passed | `test_core.py`; PNG responses |
| Reports protected; audit trail | Passed | access tests; audit tests |
| Migrations, checks, lint, tests, coverage gate | Passed | 222 tests, 96% / 99% |
| Jenkinsfile quality gates present and commands working | Passed (rehearsal) | `rehearse_jenkinsfile.py` SUCCESS |
| Jenkins pipeline executed on a Jenkins server | **Not verified** | No Jenkins available; steps in README |
| Automated accessibility (WCAG 2.2 AA rules), keyboard, focus, reflow | **Failing: colour contrast** (since the paper-theme redesign) | `tools/a11y` audit: `color-contrast` only; keyboard, focus, reflow pass |
| Screen-reader testing (NVDA/JAWS/VoiceOver) | **Not verified** | Accessibility tree inspected only |
| Configuration exposes no secrets | Passed | `.env` ignored; `check --deploy` |
| Code committed to Git | **Not done** | No Git identity configured; commands in README |

## Remaining / not verified

- **Jenkins:** the pipeline has never run on a real Jenkins server. Follow README → "How to run it for real".
- **Screen readers:** no manual testing has been done.
- **Git:** nothing is committed yet. Everything is staged, but the first commit needs your Git identity.
- **Deferred (Lean):** probabilistic Monte-Carlo mode and PDF export. Multi-tenant organizations and an asset-level graph are designed but not built (docs/engineering-assessment.md).
