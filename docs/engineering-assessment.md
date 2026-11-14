# CodeGuard engineering assessment

Date: 2026-10-26. Scope: the full repository as it stood after the paper/dark theme work
(237 automated tests passing, live authorization matrix 43/43, axe audit with known palette
contrast failures). The question asked: what separates this implementation from a credible,
production-minded security product, and what should be fixed first?

Severity reflects user impact and, for security items, exploitability. Effort is relative
(S = hours, M = a day, L = several days). "Status" is updated as work lands; see the bottom
of this file for what was verified.

## What is already solid (keep it)

- **Engine isolation.** `simulation/engine.py`, `risk.py`, `propagation.py` and
  `recommendations.py` have no Django imports, are deterministic and are unit-tested against
  hand calculations. Results carry `MODEL_VERSION`.
- **Historical integrity.** Each run stores a versioned snapshot of every input plus the full
  result; reports never change when scenarios are edited or deleted.
- **Object-level authorization.** Private scenarios and reports are owner-only, enforced in
  service functions, with 404 (not 403) for objects a user cannot see. Verified by tests and a
  live matrix.
- **Baseline web security.** Strict CSP (hash-allowed theme script only), CSRF on every POST,
  secure cookies and HSTS when `DEBUG` is off, fail-closed secret key, sanitized audit metadata.
- **CI discipline.** Ruff, `check --deploy`, `makemigrations --check`, coverage gate and
  `pip-audit` in both Jenkins and GitHub Actions.

## Findings

### Critical

None found. No path was found that lets one user read or change another user's private data;
this rests on the existing IDOR tests and the live authorization matrix, not on a formal audit.

### High

| # | Finding | Impact | Effort | Status |
|---|---|---|---|---|
| H1 | **No brute-force protection on sign-in.** Unlimited password guesses per account and per IP. Failed attempts were logged but never acted on. | Online password guessing against any account, including administrators. | S | Fixed |
| H2 | **Undefined tenancy boundary.** "Shared" means *every account on the instance*, and self-registration is open and grants the Analyst role. On any internet-reachable deployment a stranger can register, read all shared scenarios and reports, and run simulations. | Data exposure across teams; the access model does not match how a security team would use the product. | S (registration policy) / L (organizations) | Registration policy fixed; organizations need a product decision (see below) |
| H3 | **Audit log immutability is partial.** `AuditEvent.save()` refuses updates, but `QuerySet.update()`, `QuerySet.delete()` and bulk operations bypass it. | A code path (or a future developer) can silently rewrite or erase audit history. | S | Fixed at the ORM layer; database-level triggers remain future work |
| H4 | **Colour contrast below WCAG AA** in four light-theme palette pairs and the dark primary button. | Low-vision users; fails the project's own accessibility requirement. | S | Open: palette values are a design decision awaiting approval |

### Medium

| # | Finding | Impact | Effort | Status |
|---|---|---|---|---|
| M1 | **No health endpoint, no request correlation, plain-text logs only.** | Load balancers and monitors cannot probe the app; log lines from one request cannot be tied together; logs are hard to ingest. | S | Fixed |
| M2 | **SQLite is used with default settings.** Deferred transactions and no busy timeout produce "database is locked" errors as soon as two worker processes write. No documented position on PostgreSQL. | Intermittent failures under modest concurrency. | S | Fixed (WAL, immediate transactions, busy timeout) and decision recorded |
| M3 | **No backup, restore or retention procedure.** | Data loss on disk failure; unbounded audit growth. | S | Fixed (online backup command, documented restore and retention) |
| M4 | **Recommendations are not actionable.** A report lists controls to adopt, but nothing records who will do it, its status, or whether a re-run confirmed the improvement. | Users cannot manage remediation, which is the main reason a security team would use the tool. | M | Fixed (remediation plan) |
| M5 | **Control effectiveness is a bare number.** Controls have no stated basis, assumptions or limitations, so an illustrative parameter reads like a measured fact. | Misleading risk communication. | S | Fixed |
| M6 | **No production deployment path.** No WSGI server guidance, static-file serving, TLS/proxy settings walkthrough or operational checklist. | A reviewer cannot see how this would actually be run. | S | Fixed (deployment guide) |
| M7 | **Fixed five-stage asset model.** Scenarios cannot describe concrete assets (repositories, runners, registries, clusters) or trust relationships between them. | Limits realism for non-teaching use. | L | Future: design below |
| M8 | **Deterministic single-point model.** One likelihood, one threshold, no uncertainty range. | Results can look more precise than they are. | M | Documented limitation; Monte-Carlo mode remains future work |

### Low

| # | Finding | Status |
|---|---|---|
| L1 | Simulations run synchronously inside the request. Fine at current cost (milliseconds); revisit only if the model grows. | Accepted |
| L2 | Django admin is mounted at `/admin/` in every environment. It is superuser-only, but it is outside the app's CSP and audit trail. | Documented; disable or restrict at the proxy in production |
| L3 | Fonts were loaded from Google Fonts: a third-party request on every page view. | Fixed 2026-11-14: the three typefaces are vendored in `static/vendor/fonts` and the CSP allows no outside origin |
| L4 | The Jenkinsfile has never run on a Jenkins server; screen-reader testing has not been done. | Open (requires external resources) |

## Decision needed: organizations (H2)

Two credible models:

1. **Single-tenant deployment (one organization per instance).** Common for self-hosted
   security tools. The tenancy boundary is the deployment; registration must therefore be
   controlled. Implemented now: `CODEGUARD_REGISTRATION=open|domain|closed` with an allowed
   email-domain list, plus a `check --deploy` warning when registration is open in production.
2. **Multi-tenant organizations.** An `Organization` model, memberships with per-organization
   roles, and every scenario, run, remediation item and audit event scoped to an organization
   in the service layer. Correct if several unrelated teams must share one deployment, but it
   touches every query and every authorization test (estimate: L).

Option 1 is implemented because it closes the exposure without a speculative rewrite. Option 2
should be built only if multi-team hosting is an actual requirement.

## Future design: asset graph (M7)

Keep the five stages as the teaching view, and add an optional `Asset` layer (name, kind,
stage) with `TrustRelationship` edges between assets. The engine already works on a generic
directed graph (`Stage`/`Edge` domain objects), so assets can be mapped onto it without changing
the risk formulas. This is deliberately not built yet: no current workflow needs it.

## Verification of the fixes

| Item | Evidence |
|---|---|
| H1 | `TestLoginThrottling` (6 tests: lock, case-insensitivity, per-user scope, reset on success, expiry, IP limit) |
| H2 | `TestRegistrationPolicy` (closed, domain, deploy check); `scripts/ci_deploy_check.py` now reports `codeguard.W001` for the default `open` setting |
| H3 | `test_bulk_update_and_delete_are_refused`, `test_deleting_a_user_keeps_their_events`, `test_retention_purge` |
| M1 | Health, request-ID and JSON-log tests in `core/tests/test_core.py`; `/healthz/` and `X-Request-ID` checked against the running server |
| M2 | `test_sqlite_runs_in_wal_mode_with_immediate_transactions`; concurrency measurement: 4 processes × 50 real simulation runs on one file. Django defaults: 44 of 200 completed (156 failed). New settings: 200 of 200 completed |
| M3 | `test_backup_db_writes_a_verified_copy_and_rotates`; a real backup of the development database passed `integrity_check` |
| M4 | 11 tests in `remediation/tests/`; a browser journey in real Chrome (run → add to plan → update → re-run → verified; 8/8 checks); live authorization matrix extended to remediation (52/52, database unchanged) |
| M5 | `test_every_seeded_control_states_its_basis_and_limitations`, `test_snapshot_records_the_assumptions_of_enabled_controls` |
| M6 | Configuration and commands in `docs/deployment.md` are tested; the systemd and nginx snippets are **not** (labelled as examples) |

A defect found while testing M4: a bound `ModelForm` copies submitted values onto the instance
during validation, so the first version of the remediation update read the *new* status as the
old one, never set `closed_at` and would have written a wrong audit transition. A test caught it;
the service now reads the stored status under a row lock.

Not verified: a real Jenkins server run, a production deployment, and screen-reader testing.
