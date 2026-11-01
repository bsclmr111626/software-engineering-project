# CodeGuard — Test Plan

## Strategy

| Level | Tooling | Location | Database |
|---|---|---|---|
| Unit: engine, risk, recommendations | pytest | `simulation/tests/test_engine.py`, `test_risk.py`, `test_recommendations.py` | none |
| Service, view and authorisation | pytest-django, Django test client | `*/tests/` | isolated temporary SQLite |
| Integration and journeys | pytest-django | `tests/test_integration.py` | isolated temporary SQLite |
| Static | Ruff, `manage.py check`, `makemigrations --check` | CI | — |
| Security configuration | `manage.py check --deploy`, `pip-audit` | CI | — |
| Visual and manual | Headless Chrome screenshots of the landing, overview, supply chain, threat library, configuration stepper, results, risk analysis, settings and sign-in pages at 1440px and 390px, light and dark | manual | dev DB |
| Design system (static) | Colours only inside the token region; both themes and every variant define the same tokens; no theme branching, colour gradients or uppercase labels; every preference value has a style hook; chart palette matches the light tokens | `core/tests/test_design.py` | none |
| Settings and preferences | Each settings page renders and saves only its own fields; preferences reach `<html>` and the views (page size, timestamps, start page, share-by-default); email change needs the password; session revocation signs out other sessions; data export is own-data only; admin-only pages | `accounts/tests/test_settings.py` | isolated |
| Product areas | Supply chain, stage detail, risk analysis, hub, results, result tabs, report documents, notifications and SVG chart geometry, all scoped to what the user may see | `core/tests/test_areas.py` | isolated |
| Accessibility (automated) | axe-core 4.10.2 in real Chrome: WCAG 2.0/2.1/2.2 A+AA and best practice at 1280px and 390px; keyboard focus visibility; reflow; error states | `tools/a11y/audit.mjs`, `errstates.mjs` | dev DB (running server) |
| Accessibility (server-side regression) | Error/help IDs exist for every `aria-describedby`; table, diagram and chart names; `aria-current`; no auto-submit; button contrast token | `core/tests/test_accessibility.py` | isolated |
| End-to-end in a browser | Register → scenario → keyboard-only run → inspect propagation → enable controls with Space → compare → reopen report | `tools/a11y/journey.mjs` | dev DB (running server) |
| Live authorization | Second analyst, viewer and anonymous attack a victim's private scenario and reports over HTTP with valid CSRF tokens; DB unchanged | `tools/authz_live.py` | dev DB (running server) |
| CI rehearsal | Every Jenkinsfile stage command on a clean checkout with a fresh venv | `scripts/rehearse_jenkinsfile.py` | isolated CI DB |
| Concurrency | 4 processes × 50 real simulation runs on one SQLite file, comparing Django's default SQLite settings with the project's | one-off script (method in docs/architecture.md, section 9); settings pinned by `test_sqlite_runs_in_wal_mode_with_immediate_transactions` | temporary file DBs |

Expected values in the engine tests are calculated by hand from the documented formulas. The core calculations are never mocked; the only mock is used to simulate an unexpected failure during a run.

Run the suite with `pytest`, or `pytest --cov` for coverage. The core coverage gate is ≥ 85% on `engine.py`, `risk.py`, `propagation.py` and `recommendations.py`.

## Requirement → test traceability

| Req. | Test case(s) | Expected result |
|---|---|---|
| FR-01 | `test_registration_creates_user_with_default_role_and_logs_in`, `test_weak_password_is_rejected`, `test_duplicate_email_is_rejected`, `test_password_is_hashed` | User created with the analyst role; weak, duplicate or plaintext cases rejected |
| FR-02 | `test_successful_login`, `test_invalid_credentials`, `test_logout_requires_post_and_ends_session`, `test_password_change_is_audited`, `test_password_reset_sends_email_without_disclosing_accounts` | Correct redirects; session ended; reset email sent only for real accounts with an identical response |
| FR-03 | `test_protected_pages_require_login`, `test_anonymous_users_are_redirected_to_login` | 302 to the login page |
| FR-04 | `test_viewer_cannot_run_simulations`, `test_viewer_cannot_create_or_clone`, `test_analyst_cannot_edit_shared_scenario` | 403 and no data changed |
| FR-05 | `test_role_cannot_be_chosen_during_registration`, `test_admin_can_change_role`, `test_admin_cannot_change_own_role`, `test_invalid_role_rejected`, `test_analyst_cannot_change_roles`, `test_viewer_cannot_change_roles` | Only admins change other users' roles; the change is audited |
| FR-06 | `test_seed_creates_reference_data` | Five ordered stages |
| FR-07 | `test_library_lists_shared_scenarios`, `test_search_and_filters` | Correct filtered results |
| FR-08 | `test_seed_creates_reference_data`, `test_every_seeded_scenario_simulates_successfully` | Six complete scenarios, all simulate successfully |
| FR-09 | `test_analyst_creates_private_scenario`, `test_admin_can_create_shared_scenario`, `test_edit_increments_version`, `test_archive_and_restore`, `test_delete_requires_confirmation_and_post`, `test_clone_copies_rules_and_controls`, `test_system_scenario_cannot_be_deleted_even_by_admin` | CRUD respects ownership; the version increments; system scenarios are protected |
| FR-10 | `test_invalid_graph_rejected` (self-loop, duplicate, unreachable), `test_rule_probability_validated`, `TestConstraints` | Form errors and DB constraint errors |
| FR-11 | `test_seed_is_idempotent`, `test_seed_does_not_overwrite_admin_edits_unless_reset`, `test_demo_users_*` | No duplicates; demo users only in DEBUG |
| FR-12 | `test_configure_prefills_scenario_values`, `test_post_runs_simulation_and_redirects`, `test_out_of_range_values_are_rejected`, `test_cannot_run_another_users_private_scenario` | Run created only for valid, authorised input |
| FR-13 | `TestPropagation` (full chain, below threshold, inclusive threshold boundary, 0% and 100% edges, bypass, reverse, max path, cycles, no rules, affected and unaffected) | Exact states and likelihoods |
| FR-14 | `TestRawAndResidualRisk`, `TestCombinedEffectiveness`, `TestRoundingAndClassification`, `test_overall_risk_is_weighted_average`, `TestControls` | Values match the hand calculations |
| FR-15 | `test_owner_sees_report_with_charts`, `test_every_seeded_scenario_simulates_successfully` | Report renders with the pipeline, stages and events |
| FR-16 | `test_recommendation_reports_exact_modeled_reduction`, `test_recommendations_are_ranked_by_reduction`, `test_enabled_and_useless_controls_are_not_recommended` | Exact reductions, correct ranking |
| FR-17 | `test_before_after_comparison`, `test_rerun_prefills_from_previous_run`, `test_complete_analyst_journey` | Negative delta; state changes detected |
| FR-18 | `test_historical_report_is_stable_after_scenario_edit`, `test_run_survives_scenario_deletion`, `test_snapshot_reproduces_the_stored_result` | Stored results unchanged; snapshot reproduces them |
| FR-19 | `test_history_lists_only_own_runs_by_default`, `test_csv_export_contains_results_and_is_audited`, `test_history_csv_contains_only_own_runs`, `test_shared_report_visible_read_only_to_viewer` | Correct scoping |
| FR-20 | `test_owner_sees_report_with_charts`, `test_before_after_comparison`, `test_dashboard_metrics_reflect_database` | Valid PNG responses |
| FR-21 | `test_dashboard_empty_state`, `test_dashboard_metrics_reflect_database`, `test_dashboard_excludes_other_users_private_runs` | Metrics equal values computed independently from the DB |
| FR-22 | `test_control_list_and_filters`, `test_control_detail` | 14 controls; filters work |
| FR-23 | Audit assertions in the auth, scenario, simulation and role tests; `test_scenario_actions_are_audited` | Events recorded with safe metadata |
| FR-24 | `test_non_admin_sees_only_own_events`, `test_admin_sees_all_events_and_can_filter` | Correct scoping |
| FR-25 | `test_methodology_page_is_public_and_shows_formulas` | Formulas and disclaimer present |
| NFR-01 | `test_identical_inputs_give_identical_results`, `test_edge_order_does_not_change_result` | Identical output |
| NFR-03 | `test_login_form_enforces_csrf`, `test_csrf_failure_page`, `test_security_headers_present`, `test_open_redirect_is_ignored`, IDOR tests, `test_csv_cells_are_protected_against_formula_injection` | Attacks are rejected |
| NFR-04 | `test_sensitive_metadata_is_removed`, `test_invalid_credentials` (no password in the audit log) | No secrets stored |
| NFR-05 | `test_failure_marks_run_failed_without_partial_results`, `test_invalid_configuration_creates_no_run` | No partial results |
| NFR-06 | Coverage gate | Core coverage ≥ 85% (measured: 99%) |
| NFR-07 | `core/tests/test_accessibility.py`; `tools/a11y` audit (24 pages × 2 widths), error states (5), keyboard-only journey | 0 axe violations; visible focus on every tab stop; no reflow overflow; errors announced via `aria-invalid` and `aria-describedby` |
| FR-04/09/19/28 (live) | `tools/authz_live.py` | 52/52: other users get 404 (or a uniform 403 for viewers), including remediation items; forged POSTs are rejected visibly; DB unchanged |
| FR-26 | `TestLoginThrottling` | Lock after 5 failures per username or 20 per IP; refused before the password check; expires after 15 minutes; reset on success |
| FR-01 (policy) | `TestRegistrationPolicy` | `closed` refuses and hides links; `domain` accepts only listed domains; deploy check warns when `open` |
| FR-27 | `test_every_seeded_control_states_its_basis_and_limitations`, `test_snapshot_records_the_assumptions_of_enabled_controls` | Every control documented; snapshot unchanged by later catalog edits |
| FR-28 | `remediation/tests/test_remediation.py` (11 tests); browser journey 8/8 | Tracking, de-duplication (also at DB level), ownership, status transitions, verification, audit |
| FR-29 | Health, request-ID, JSON-log, backup and retention tests in `core/tests/test_core.py` and `audit/tests/test_audit.py` | Probe minimal; IDs sanitised; backup verified and rotated; purge audited, ≥ 30 days |
| T14 | `test_bulk_update_and_delete_are_refused`, `test_deleting_a_user_keeps_their_events` | Audit history cannot be rewritten through the ORM |
| CI | `tests/test_ci_scripts.py`; `scripts/rehearse_jenkinsfile.py` | Audit exit codes are correct for clean, vulnerable and unreachable cases; all stage commands succeed on a clean checkout |
| — | `test_migrations_are_consistent_with_models`, `test_system_checks_pass`, `test_every_main_page_renders_for_analyst`, error-page tests | Project integrity |

## Boundary values covered

- Likelihood −1, 0, 100 and 100.1, plus NaN and infinity.
- Severity and impact 0, 1, 5 and 6.
- Threshold 0 (rejected), 50 (inclusive) and 100.
- Edge probability 0, 49, 50, 100 and 120.
- Control effectiveness 100 and 101.
- Combined coverage with several 90% controls (≤ 100).
- Rounding half-up at 12.25 → 12.3 and 99.95 → 100.0.
- Classification bands at 15, 30 and 50.

## Last execution

| Date | Environment | Result |
|---|---|---|
| 2026-10-26 (round 1) | Windows 11, Python 3.12.10, Django 5.2.18 | 210 passed; total coverage 96%; core 99%; Ruff clean; `pip-audit` reported no known vulnerabilities |
| 2026-10-26 (round 2, independent re-verification) | Same machine, Chrome (headless), Node 24, axe-core 4.10.2 | 222 passed; 96% / 99% coverage; Jenkinsfile rehearsal SUCCESS on a clean checkout; axe 0 violations (24 pages × 2 widths, plus 5 error states); keyboard journey 14/14; live authorization 43/43. **Not executed:** Jenkins server run, real screen-reader testing. |
| 2026-10-26 (paper-theme redesign) | Same machine and tools | 226 passed; Ruff clean; axe: `color-contrast` only, from 4 DESIGN.md palette pairs (22 pages, 4 of 5 error states); keyboard focus and reflow pass on every page. |
| 2026-10-26 (dark mode) | Same machine and tools | 231 passed; Ruff clean; theme behaviour 9/9 in real Chrome (OS default, live OS change, saved choice wins before paint, chart redraw, no CSP errors); axe light: unchanged (4 palette pairs); axe dark: `color-contrast` only on the primary button (white on `--accent` 3.58:1); keyboard focus and reflow pass in both themes. |
| 2026-10-26 (engineering review round) | Same machine and tools | 268 passed; 96% total and 99% engine coverage; Ruff clean; Jenkinsfile rehearsal on a clean checkout SUCCESS; `pip-audit` no known vulnerabilities; live authorization matrix 52/52 with remediation items (database unchanged); remediation browser journey 8/8; SQLite concurrency 200/200 runs completed (Django defaults 44/200); axe: 24 pages in both themes, `color-contrast` only (palette). **Not executed:** Jenkins server run, production deployment, screen-reader testing. |
| 2026-10-28 (product redesign) | Same machine; Chrome (headless), Node 24, axe-core 4.10.2 | 332 passed; 96% total coverage; Ruff and `makemigrations --check` clean; axe 0 violations on 47 pages at 1280px and 390px in both themes, keyboard focus visible on every tab stop and no reflow overflow; error states 5/5; keyboard journey 14/14 through the new stepper and result tabs; live authorization matrix extended to result tabs, report documents, admin-only settings and the data export, all passed; `check --deploy` 0 errors and the same 3 intentional warnings. **Not re-run this round:** Jenkinsfile rehearsal, `pip-audit`, the SQLite concurrency test and the remediation browser journey. **Not executed:** Jenkins server run, production deployment, screen-reader testing. |
