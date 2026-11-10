# Security

This document describes the security controls **of the CodeGuard application itself** (not the
simulated supply-chain controls), what evidence exists for each, and the gaps. The project's
own STRIDE analysis is in `docs/threat-model.md`; findings and fixes are in
`docs/engineering-assessment.md`. Diagram: [authentication](diagrams/authentication.md).

Status labels: **verified** = implemented and covered by a test that passed on 2026-11-10;
**unverified** = implemented, no test found; **partial**; **not implemented**.

No penetration test or formal audit has been done. Passing tests do not prove the absence of
vulnerabilities (README says the same).

## 1. Authentication

**What it is.** Proving who a user is. CodeGuard uses Django's session authentication with the
built-in `User` model and password hashing (PBKDF2 by default in production settings; the test
settings switch to MD5 purely for speed).

| Control | How | Evidence | Status |
|---|---|---|---|
| Password policy | `AUTH_PASSWORD_VALIDATORS`: similarity, **min length 10**, common-password list, not all numeric | `test_weak_password_is_rejected` | verified |
| Passwords hashed | Django hasher | `test_password_is_hashed` | verified |
| Sign-in throttling | `ThrottledAuthenticationForm.clean()` calls `throttling.is_locked()` **before** the password is checked. Defaults: 5 failures per username, 20 per client IP, within 15 minutes. Failures before the account's last successful sign-in are not counted. A locked account stays locked even with the right password | `TestLoginThrottling` (6 tests) | verified |
| Failed attempts recorded without passwords | `signals.on_login_failed` stores only `attempted_username` (truncated to 150) | `test_sensitive_metadata_is_removed`, throttling tests | verified |
| Password reset | Django `PasswordResetView`; email via console backend by default, SMTP configurable; response does not reveal whether an account exists | `test_password_reset_sends_email_without_disclosing_accounts` | verified |
| Password change audited | `AuditedPasswordChangeView.form_valid` → `password_change` event | `test_password_change_is_audited` | verified |
| Email change needs the current password | `settings_views.account` | `test_email_change_requires_the_current_password` | verified |
| Logout requires POST | Django 5 `LogoutView` | `test_logout_requires_post_and_ends_session` | verified |
| Open-redirect protection on login | Django's `next` validation | `test_open_redirect_is_ignored` | verified |
| Multi-factor authentication for CodeGuard accounts | — | — | **not implemented** (MFA appears only as a *simulated* control) |

**Throttling trade-off (from the docstring of `accounts/throttling.py`).** Anyone can lock an
account for 15 minutes by guessing wrongly five times. Counting is done from audit events in the
database, so it works across worker processes without a cache server.

**Gap: client IP behind a proxy.** `audit.services.client_ip` deliberately trusts only
`REMOTE_ADDR` ("X-Forwarded-For is client-controlled unless a trusted proxy is configured").
Behind a reverse proxy every request has the proxy's address, so the per-IP limit (20) becomes a
limit shared by **all** users, and audit events record the proxy IP. `docs/deployment.md`
mentions raising the IP limit for shared NAT addresses but not this proxy effect. Status:
**partial**.

## 2. Sessions

| Control | Setting / code | Status |
|---|---|---|
| HttpOnly session cookie | `SESSION_COOKIE_HTTPONLY = True` | configured (Django default behaviour, not separately tested) |
| SameSite=Lax cookies | `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE` | configured |
| 8-hour lifetime, ends at browser close | `SESSION_COOKIE_AGE = 28800`, `SESSION_EXPIRE_AT_BROWSER_CLOSE = True` | configured |
| Secure cookies when DEBUG is off | `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` default to `not DEBUG` | covered by `check --deploy` |
| "Sign out of other sessions" | `UserPreference.session_epoch`; `revoke_sessions` increments it and stores the new value in the current session; `SessionEpochMiddleware` logs out any session whose stored epoch differs | `test_signing_out_other_sessions` — verified |
| Session list | `/settings/sessions/` shows the current session (start time, a short user-agent description from `describe_agent`) and recent sign-ins from the audit log; Django's database sessions are not enumerated | verified (`test_sessions_page_describes_this_session`) |

## 3. Authorization

**What it is.** Deciding what an authenticated user may do. CodeGuard has three roles stored in
`accounts_profile.role` and resolved by `accounts.permissions.get_role` (superusers are always
admin; a missing profile means viewer). Templates hide buttons for convenience, but the module
docstring is explicit: "every protected view calls these helpers… so authorization never depends
on what the browser shows."

### 3.1 Role matrix (from decorators and service checks)

| Capability | Viewer | Analyst | Admin |
|---|---|---|---|
| Read shared scenarios, controls, stages, help | ✓ | ✓ | ✓ |
| Read own private scenarios | — (cannot create) | ✓ | ✓ |
| Create / clone scenarios (always private) | ✗ | ✓ | ✓ (may publish as shared) |
| Edit / archive a scenario | ✗ | own private only | own private + all shared |
| Delete a scenario | ✗ | own private, never system | same; system scenarios never |
| Run simulations | ✗ (`analyst_required`) | ✓ | ✓ |
| View reports | own + shared completed | own + shared completed | own + shared completed (no special access to private runs) |
| Share / unshare a report | — | owner only | owner only |
| Add to / update the remediation plan | ✗ | own items | own items |
| Audit log | own events | own events | all events, filter by user |
| Users and roles, organization page | ✗ | ✗ | ✓ (cannot change own role or a superuser's) |

Evidence: `TestRoles`, `TestScenarioPermissions`, `TestConfigureView::test_viewer_cannot_run_simulations`,
`TestReportAccess`, `test_viewers_cannot_track_and_strangers_cannot_reach_private_runs`,
`test_administration_pages_are_admin_only`, `test_admin_cannot_see_other_users_private_scenarios`.
Status: **verified**.

### 3.2 Object-level access (IDOR protection)

All lookups go through scoped querysets, and misses return **404, not 403**, so the existence
of another user's object is not revealed:

* `threats.services.visible_scenarios(user)`: `Q(visibility="shared") | Q(owner=user)`.
* `simulation.services.accessible_runs(user)`: `Q(user=user) | Q(is_shared=True, status="completed")`;
  `get_accessible_run` also catches malformed UUIDs (`ValueError`).
* `remediation.services.items_for(user)`: `owner=user`.
* `SimulationForm.__init__` limits the scenario choice to *active, visible* scenarios, so "a
  forged POST cannot run another user's private scenario"
  (`test_cannot_run_another_users_private_scenario`).
* `test_viewer_role_denial_does_not_reveal_whether_a_private…` checks that the role denial
  happens before the lookup.

A live HTTP authorization matrix (`tools/authz_live.py`, run as a second analyst, a viewer and
anonymously, with real CSRF tokens) passed according to the README; it was **not re-run** for
this documentation.

### 3.3 Registration and the tenancy boundary

`RegistrationForm` has no role field; `signals.create_profile` assigns
`CODEGUARD_DEFAULT_ROLE` (only `analyst` or `viewer` are accepted by settings). Who may register
is set by `CODEGUARD_REGISTRATION`: `open` (default), `domain` (with
`CODEGUARD_REGISTRATION_DOMAINS`) or `closed`. With DEBUG off and registration open,
`manage.py check --deploy` warns `codeguard.W001`. Verified by `TestRegistrationPolicy` and by
running `scripts/ci_deploy_check.py` (warning present).

**Gap (documented, by design).** "Shared" means every account on the instance; there are no
organizations. With the default `open` registration on a public host, a stranger can register as
an analyst and read every shared scenario and report. Status: single-tenant model
**implemented**; multi-tenant organizations **not implemented** (assessment H2).

## 4. Request integrity and browser hardening

| Control | Implementation | Evidence | Status |
|---|---|---|---|
| CSRF | `CsrfViewMiddleware`; every form has `{% csrf_token %}`; state changes use POST (`require_POST` on share, archive, clone, track, revoke, role change, notifications read, theme) | `test_login_form_enforces_csrf`, `test_archive_requires_post`, `test_csrf_failure_page` | verified |
| Content-Security-Policy | `core/middleware.py`: `default-src 'self'`; `script-src 'self'` plus the SHA-256 hash of the one inline theme script (`core/theme.py`); styles and fonts from self and Google Fonts; `img-src 'self' data:`; `form-action 'self'`; `frame-ancestors 'none'`; `object-src 'none'`; `base-uri 'self'` | `test_security_headers_present`, `test_theme_script_runs_first_and_is_the_only_inline_script_the_csp_allows` | verified |
| Clickjacking | `X_FRAME_OPTIONS = "DENY"` plus `frame-ancestors 'none'` | header test | verified |
| Other headers | `nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()` | header test | verified |
| HTTPS | `SECURE_SSL_REDIRECT`, HSTS 3600 s by default when DEBUG is off; `/healthz/` exempt from the redirect | `check --deploy` | configured; HTTPS itself not exercised (no TLS server here) |
| Template auto-escaping | Django default. `mark_safe` appears only for fixed markup in `core/templatetags/codeguard_tags.py` (theme script, level ticks); the `safe` filter only on developer-defined form `help_text` (`components/field.html`, `registration/_simple_form.html`) | — | unverified (no dedicated XSS test) |
| CSV formula injection | `simulation/exports.safe_cell` prefixes `'` to cells starting with `= + - @ \t \r` | `test_csv_cells_are_protected_against_formula_injection` | verified |
| Safe redirects | `quick_theme` validates `next` with `url_has_allowed_host_and_scheme` | `test_quick_theme_toggle_saves_the_color_mode` | verified |
| Error pages | custom 400/403/404/500 and CSRF pages; no stack traces when DEBUG is off | `test_custom_404_page_has_no_debug_details`, `test_server_error_page_hides_details` | verified |
| Health endpoint discloses nothing | returns only `status` and `database` | `test_health_check_is_public_and_minimal` | verified |

**Exclusions.** The CSP header is not sent for `/admin/` (the middleware skips it), and the
Django admin's own changes are not written to the CodeGuard audit trail. `docs/deployment.md`
suggests restricting `/admin/` at the proxy. Status: **partial**.

## 5. Secrets and configuration

* `DJANGO_SECRET_KEY` is required when DEBUG is off (`ImproperlyConfigured` otherwise). A fixed
  development fallback exists only when DEBUG is true.
* `.env` is git-ignored (`.env`, `.env.*`, with `!.env.example`); `.env.example` contains only
  placeholders. The local `.env` was not opened for this documentation.
* `scripts/ci_deploy_check.py` generates a random throw-away key per process and never prints it.
* The demo accounts' password is published in the README on purpose. The seed command refuses
  `--demo-users` unless DEBUG is true (`test_demo_users_refused_outside_debug`), but a database
  seeded in development and then deployed would still contain them. Status: **partial** (no
  check warns about demo users in production).
* Ruff runs the Bandit-derived `S` rules on all code; test passwords are allow-listed per file in
  `pyproject.toml`.

## 6. Audit trail and privacy

`audit.services.record_event` is called for sign-in, sign-out, failed and throttled sign-in,
registration, password/email change, scenario create/update/archive/restore/delete/clone,
simulation run/failure, report share/export, role change, audit purge, remediation create/update,
profile and preference updates, session revocation and personal data export (the 25
`AuditAction` values). It stores actor, username, action, object type/id/repr, sanitised
metadata and `REMOTE_ADDR`.

* `sanitize_metadata` drops keys containing `password`, `secret`, `token`, `session`, `csrf`,
  `key` or `credential`, and truncates values to 200 characters and lists to 50 items.
* Append-only at the ORM level (see `DATABASE_AND_MIGRATIONS.md` §1.4); deleting a user keeps
  their events with `actor = NULL`.
* Retention: `purge_audit_events --days N` (minimum 30, `--dry-run`, records its own run).
* Personal data export: `/settings/privacy/export.json` returns only the user's own data and is
  audited (`test_data_export_contains_only_own_data_and_is_audited`).

Gaps: no database-level immutability (triggers), no tamper-evident chaining, no off-host log
shipping; IP addresses are personal data and `docs/deployment.md` §8 says to cover them in a
privacy notice.

## 7. Supply chain of CodeGuard itself

All Python dependencies are pinned in `requirements.txt` and `requirements-dev.txt`;
`scripts/ci_dependency_audit.py` runs `pip-audit` with explicit exit codes (0 clean, 1 vulnerable,
2 incomplete). It reported "No known vulnerabilities" when re-run on 2026-11-10, and the same
check passes in GitHub Actions (run #7). Bootstrap and Bootstrap Icons are vendored (no CDN), but their versions
are not recorded in the repository. Hashes (`--require-hashes`) are not used.

## 8. Summary of gaps

| Gap | Severity (author's judgement) | Status |
|---|---|---|
| Reports templates were not in Git: a deployment from the repository served 500 errors on `/reports/` | high (availability) | fixed in commit `eef6716` |
| No MFA for CodeGuard accounts | medium | not implemented |
| Per-IP throttling collapses to one shared bucket behind a proxy | medium | open |
| Open registration by default, single-tenant sharing | medium | documented; mitigated by settings and `W001` |
| Admin outside CSP and audit trail | low | documented |
| Audit immutability only in the ORM | low | documented |
| Demo users could survive into production | low | partial |
| Unpinned `requests` for `tools/authz_live.py`; vendored asset versions unknown | low | open |
| No penetration test, no screen-reader test | — | not done |
