# CodeGuard — Threat Model (of the application itself)

This document analyses threats to the CodeGuard web application, not the simulated supply chain. It follows a lightweight STRIDE approach.

## 1. Assets

| Asset | Why it matters |
|---|---|
| User credentials and sessions | Account takeover would expose private scenarios and reports. |
| Private scenarios and reports | They may describe an organisation's real weaknesses. |
| Role assignments | Escalation to admin would grant control over shared data and roles. |
| Audit log | Accountability; it must be trustworthy and must not leak secrets. |
| `DJANGO_SECRET_KEY` | Signs sessions, CSRF tokens and password-reset tokens. |
| Seed and reference data | The integrity of every simulation depends on it. |

## 2. Actors

- Anonymous internet user
- Authenticated viewer, analyst or administrator
- A malicious insider holding a legitimate low-privilege account
- An operator with server access, who is trusted

## 3. Trust boundaries and attack surface

1. **Browser ↔ web server.** This covers all HTTP endpoints: auth forms, scenario CRUD, the simulation form, report, chart and CSV endpoints, role changes, and the Django admin.
2. **Application ↔ database.** This is local SQLite, accessed only through the ORM.
3. **Application ↔ email.** Password-reset emails (the console backend locally).
4. **CI ↔ repository.** Jenkins checks the code out and runs it with no deployment credentials.

## 4. Threats and mitigations (STRIDE)

| # | Threat | Category | Mitigation in CodeGuard | Verified by |
|---|---|---|---|---|
| T1 | Credential stuffing or brute-force login | Spoofing | Django password hashing (PBKDF2); validators (minimum 10 characters, common and numeric checks); failed logins audited; sign-in throttling: 5 failures per username or 20 per client IP within 15 minutes lock further attempts, refused before the password is checked and audited as `login_throttled` | `test_auth.py` (`TestLoginThrottling`, weak password, failed-login audit) |
| T2 | Session hijacking | Spoofing | HttpOnly and SameSite=Lax cookies; Secure cookies and HTTPS redirect plus HSTS when DEBUG is off; 8-hour expiry; logout by POST | `check --deploy`, `test_logout_requires_post…` |
| T3 | Self-registration as admin (mass assignment) | Elevation | Registration form has no role field; role set server-side; admin only via `createsuperuser` or another admin | `test_role_cannot_be_chosen_during_registration` |
| T3b | Outsider registers on a reachable deployment and reads shared content | Info disclosure | `CODEGUARD_REGISTRATION` = `domain` (allowed email domains) or `closed`; `check --deploy` warning `codeguard.W001` when open in production | `TestRegistrationPolicy` |
| T4 | Role change by a non-admin, or self-promotion | Elevation | `admin_required` decorator; admins cannot change their own role; superusers are fixed | `TestRoles` |
| T5 | IDOR: reading another user's scenario, report, chart or CSV by ID | Info disclosure | All lookups go through ownership-filtered querysets and return 404; run IDs are UUIDv4 | `test_other_user_cannot_open_private_report_chart_or_csv`, `test_private_scenario_hidden_from_other_users` |
| T6 | Running a simulation on another user's private scenario via a forged POST | Elevation | Form queryset limited to visible, active scenarios | `test_cannot_run_another_users_private_scenario` |
| T7 | CSRF on state-changing actions | Tampering | `CsrfViewMiddleware`; every mutation is POST-only (`require_POST`) | `test_login_form_enforces_csrf`, `test_csrf_failure_page`, `test_archive_requires_post` |
| T8 | Stored XSS through scenario text | Tampering | Django auto-escaping (no `|safe` on user data); strict CSP with no inline scripts | CSP header test; templates reviewed |
| T9 | SQL injection | Tampering | ORM only; no raw SQL | Code review (`grep raw(`/`cursor` returns nothing) |
| T10 | CSV / formula injection in exports | Tampering | Cells beginning with `= + - @ \t \r` are prefixed with `'` | `test_csv_cells_are_protected_against_formula_injection` |
| T11 | Open redirect after login | Spoofing | Django `LoginView` validates `next` with `url_has_allowed_host_and_scheme` | `test_open_redirect_is_ignored` |
| T12 | Clickjacking | Tampering | `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'` | `test_security_headers_present` |
| T13 | Secrets leaking in logs, the audit log or errors | Info disclosure | Audit metadata sanitiser drops `password/secret/token/session/csrf/key/credential` keys; failed login stores only the username; custom 500 page; simulation errors shown generically | `test_sensitive_metadata_is_removed`, `test_failure_marks_run_failed…`, `test_server_error_page_hides_details` |
| T14 | Tampering with or deleting audit history | Repudiation | `AuditEvent.save()` and `delete()` refuse changes; the model's QuerySet refuses bulk `update()` and `delete()`; admin site is read-only; the only deletion path is the retention command, which audits itself | `test_events_are_append_only`, `test_bulk_update_and_delete_are_refused`, `test_retention_purge` |
| T15 | Partial or misleading results after an error | Tampering | The run is written in `transaction.atomic`; on error it is marked FAILED and child rows are rolled back | `test_failure_marks_run_failed_without_partial_results` |
| T16 | Historical reports altered by later edits | Tampering | Versioned snapshots; denormalised results; `SET_NULL` | `test_historical_report_is_stable_after_scenario_edit` |
| T17 | Path traversal through chart or file endpoints | Info disclosure | Charts are rendered in memory; the `kind` parameter is allow-listed; nothing is read from disk | `test_unknown_chart_kind_is_404` |
| T18 | Resource exhaustion from large graphs | DoS | Rule formset `max_num=20`; the graph has only 5 nodes; traversal is O(E); recommendations are bounded by the catalog size | Engine design |
| T19 | Vulnerable dependencies | Supply chain | Pinned requirements; `pip-audit` in CI; Django LTS | `pip-audit` result: no known vulnerabilities (2026-10-26) |
| T20 | Insecure production configuration | Misconfiguration | `SECRET_KEY` required when DEBUG is off; secure defaults switch on automatically; `check --deploy` in CI | `manage.py check --deploy` |
| T22 | Existence disclosure through different error codes | Info disclosure | Ownership-filtered lookups return 404. Role checks run before any lookup, so a viewer gets the same 403 for real and non-existent slugs | `test_viewer_role_denial_does_not_reveal_whether_a_private_scenario_exists`; `tools/authz_live.py` |
| T23 | Forged form value naming another user's private scenario | Elevation | The form queryset only contains visible, active scenarios; the request is rejected with a visible error and no run is created | `test_cannot_run_another_users_private_scenario`; live matrix (DB unchanged) |
| T24 | CI secret handling and sandbox escapes in the pipeline | Supply chain | The Jenkinsfile only runs commands. Secrets for `check --deploy` are generated inside `scripts/ci_deploy_check.py` and never printed; no Groovy script approvals are needed | `tests/test_ci_scripts.py` |
| T21 | Account enumeration via password reset | Info disclosure | Identical response whether the email exists or not | `test_password_reset_sends_email_without_disclosing_accounts` |
| T25 | Log injection through a forged request ID | Tampering | Incoming `X-Request-ID` is reused only if it matches `[A-Za-z0-9._-]{1,64}`; otherwise a new ID is generated | `test_request_id_is_generated_or_propagated` |
| T26 | Information leak from the health endpoint | Info disclosure | `/healthz/` returns only up/down; failures are logged server-side, not returned | `test_health_check_reports_database_failure` |
| T27 | Tampering with another user's remediation plan | Elevation | Items are owner-only (404 for others, including administrators); tracking requires the Analyst role and an accessible run; only recommended controls can be tracked | `remediation/tests/test_remediation.py` |

## 5. Residual risks and limitations

- **Account lockout can be triggered by others.** Throttling locks a username for up to 15 minutes after 5 failures, whoever caused them. This is the usual trade-off of per-account limits; the lock is short and every attempt is audited. A reverse-proxy rate limit is still advisable in front of `/accounts/login/`.
- **Registration defaults to `open`** to keep local development and classroom use simple. Production deployments must set `CODEGUARD_REGISTRATION` to `domain` or `closed`; `check --deploy` warns otherwise.
- **Audit immutability is enforced in the application**, not the database. Someone with direct database access can still alter rows; database-level triggers or shipping events to an external log store are the next step.
- **IP addresses** in the audit log come from `REMOTE_ADDR` only. Behind a proxy, every event shows the proxy's address unless the proxy is configured accordingly. `X-Forwarded-For` is deliberately not trusted.
- **SQLite** has no at-rest encryption and limited concurrency.
- **The Django admin** (`/admin/`) is excluded from the custom CSP and relies on Django's defaults. It should be restricted to administrators' networks in production.
- **`check --deploy`** leaves HSTS subdomains and preload off. These depend on the hosting domain.
- **Passing tests** do not prove the application is free of vulnerabilities. A professional review is still required before handling real data.
