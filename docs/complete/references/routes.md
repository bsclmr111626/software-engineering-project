# Reference: URL routes

Source: `codeguard/urls.py` and each included `urls.py`. "Access" is what the view itself
enforces: **public** (no login), **login** (`@login_required`), **analyst** (`analyst_required`:
admin or analyst), **admin** (`admin_required`). Object-level rules (ownership, sharing,
visibility) are listed where they apply. "POST" means the view is decorated `@require_POST`.

Root include order (`codeguard/urls.py`): `""` → core, `accounts/`, `threats/`, `simulations/`,
`reports/` (`simulation/report_urls.py`), `settings/` (`accounts/settings_urls.py`),
`remediation/`, `audit/`, `admin/`. Custom error handlers: `core.views.bad_request`,
`permission_denied`, `page_not_found`, `server_error`; CSRF failures use
`core.views.csrf_failure` (setting `CSRF_FAILURE_VIEW`).

## core (`core/urls.py`, namespace `core`)

| Path | Name | View | Access |
|---|---|---|---|
| `/` | `landing` | `landing` | public (live counts of stages, system scenarios, controls) |
| `/start/` | `start` | `start` | login; redirects to the user's chosen start page |
| `/overview/` | `dashboard` | `dashboard` | login |
| `/overview/risk-distribution.png` | `dashboard_chart` | `dashboard_chart` | login (Matplotlib PNG) |
| `/dashboard/` | `dashboard_legacy` | `dashboard_redirect` | login; permanent redirect to `/overview/` |
| `/supply-chain/` | `supply_chain` | `supply_chain` | login |
| `/supply-chain/<key>/` | `stage_detail` | `stage_detail` | login; 404 for unknown key |
| `/risk/` | `risk` | `risk` | login; `?scope=all|mine`, `?scenario=` |
| `/notifications/` | `notifications` | `notifications` | login |
| `/notifications/read/` | `notifications_read` | `notifications_read` | login, POST |
| `/help/` | `help` | `methodology` | public (layout switches on login state) |
| `/healthz/` | `healthz` | `healthz` | public, GET only, `never_cache`; exempt from the HTTPS redirect |

## accounts (`accounts/urls.py`, namespace `accounts`)

| Path | Name | View | Access |
|---|---|---|---|
| `/accounts/register/` | `register` | `views.register` | public; 403 page when `CODEGUARD_REGISTRATION=closed` |
| `/accounts/login/` | `login` | Django `LoginView` with `ThrottledAuthenticationForm` | public |
| `/accounts/logout/` | `logout` | Django `LogoutView` | POST (Django 5 requires POST for logout) |
| `/accounts/password/change/` | `password_change` | `AuditedPasswordChangeView` | login |
| `/accounts/password/change/done/` | `password_change_done` | Django view | login |
| `/accounts/password/reset/` | `password_reset` | Django `PasswordResetView` | public |
| `/accounts/password/reset/done/` | `password_reset_done` | Django view | public |
| `/accounts/reset/<uidb64>/<token>/` | `password_reset_confirm` | Django view | public, token-checked |
| `/accounts/reset/done/` | `password_reset_complete` | Django view | public |
| `/accounts/users/` | `user_list` | `RedirectView` → `settings:users` | permanent redirect (legacy link) |
| `/accounts/users/<id>/role/` | `change_role` | `views.change_role` | admin, POST |

## settings (`accounts/settings_urls.py`, namespace `settings`)

| Path | Name | View (`accounts/settings_views.py` unless noted) | Access |
|---|---|---|---|
| `/settings/` | `index` | `index` | login |
| `/settings/profile/` | `profile` | `profile` | login |
| `/settings/account/` | `account` | `account` (email change, needs current password) | login |
| `/settings/appearance/` | `appearance` | `appearance` | login |
| `/settings/appearance/quick/` | `quick_theme` | `quick_theme` (header light/dark switch) | login, POST |
| `/settings/typography/` | `typography` | `typography` | login |
| `/settings/display/` | `display` | `display` | login |
| `/settings/accessibility/` | `accessibility` | `accessibility` | login |
| `/settings/notifications/` | `notifications` | `notifications` | login |
| `/settings/privacy/` | `privacy` | `privacy` | login |
| `/settings/privacy/export.json` | `export_data` | `export_data` (own data only) | login |
| `/settings/security/` | `security` | `security` | login |
| `/settings/sessions/` | `sessions` | `sessions` | login |
| `/settings/sessions/revoke/` | `revoke_sessions` | `revoke_sessions` | login, POST |
| `/settings/organization/` | `organization` | `organization` | admin |
| `/settings/users/` | `users` | `accounts.views.user_list` | admin |
| `/settings/users/<id>/role/` | `change_role` | `accounts.views.change_role` | admin, POST |

## threats (`threats/urls.py`, namespace `threats`)

| Path | Name | View | Access |
|---|---|---|---|
| `/threats/` | `list` | `scenario_list` | login; only shared + own private scenarios |
| `/threats/new/` | `create` | `scenario_create` | analyst |
| `/threats/controls/` | `controls` | `control_list` | login |
| `/threats/controls/<slug>/` | `control_detail` | `control_detail` | login |
| `/threats/<slug>/` | `detail` | `scenario_detail` | login; 404 if not visible |
| `/threats/<slug>/edit/` | `edit` | `scenario_edit` | analyst + `can_edit` (own private; admins also shared) |
| `/threats/<slug>/archive/` | `archive` | `scenario_archive` (toggles archive/restore) | analyst + `can_edit`, POST |
| `/threats/<slug>/delete/` | `delete` | `scenario_delete` (GET confirms, POST deletes) | analyst + `can_delete` (never system scenarios) |
| `/threats/<slug>/clone/` | `clone` | `scenario_clone` (redirects to the copy's edit page) | analyst, POST; scenario must be visible |

Ordering matters: `controls/` is declared before `<slug>/`, so a scenario slug of `controls`
would be unreachable; `unique_slug()` does not reserve it (minor, not observed in practice).

## simulations (`simulation/urls.py`, namespace `simulation`)

| Path | Name | View | Access |
|---|---|---|---|
| `/simulations/` | `hub` | `hub` | login |
| `/simulations/new/` | `configure` | `configure` (`?scenario=`, `?rerun=<run id>`) | analyst |
| `/simulations/results/` | `results` | `results` (`?scope=all|mine|shared`) | login |
| `/simulations/compare/` | `compare` | `compare` (`?a=&b=`; selection page without them) | login; both runs accessible and completed |
| `/simulations/compare/chart.png` | `compare_chart` | `compare_chart` | login; same rule |
| `/simulations/<uuid>/` | `detail` | `detail` (section `summary`) | login; owner or shared+completed |
| `/simulations/<uuid>/share/` | `share` | `toggle_share` | login, POST, owner only, completed only |
| `/simulations/<uuid>/<section>/` | `detail_section` | `detail` (`summary`, `stages`, `paths`, `controls`, `method`) | login; same rule; 404 for other sections |
| `/simulations/<uuid>/chart/<kind>.png` | `chart` | `chart` (`overall`, `stages`, `outcomes`) | login; same rule; completed runs only |
| `/simulations/<uuid>/export.csv` | `export_run` | `export_run` (audited) | login; same rule |

## reports (`simulation/report_urls.py`, namespace `reports`)

| Path | Name | View (`simulation/views.py`) | Access |
|---|---|---|---|
| `/reports/` | `list` | `history` (`?scope=mine|shared|…`, `?status=`, `?q=`) | login |
| `/reports/export.csv` | `export_history` | `export_history` (own runs only, audited) | login |
| `/reports/<uuid>/` | `document` | `report_document` (printable assessment) | login; owner or shared+completed |

The Reports pages render `templates/reports/list.html` and `templates/reports/document.html`.
These two files were git-ignored until commit `eef6716` (see the master document, "Known gaps").

## remediation (`remediation/urls.py`, namespace `remediation`)

| Path | Name | View | Access |
|---|---|---|---|
| `/remediation/` | `plan` | `plan` (`?status=`, `?sort=due|impact|recent`) | login; own items only |
| `/remediation/track/` | `track` | `track` (form fields `run`, `control`) | analyst, POST |
| `/remediation/<id>/` | `detail` | `detail` (GET view, POST update) | login, own items; POST needs analyst/admin |

## audit (`audit/urls.py`, namespace `audit`)

| Path | Name | View | Access |
|---|---|---|---|
| `/audit/` | `log` | `audit_log` (`?action=`, `?user=`, `?view=timeline|table`) | login; admins see all events, others only their own |

## admin

`/admin/` — Django admin site. Superuser / staff only (Django's own check). Not covered by the
CodeGuard CSP header (`ContentSecurityPolicyMiddleware` skips paths starting with `/admin/`) and
its edits are not written to the CodeGuard audit trail.
