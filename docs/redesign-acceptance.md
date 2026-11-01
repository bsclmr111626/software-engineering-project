# Product redesign — acceptance checklist

Brief: the complete product and UI/UX redesign of 2026-10-28. Each line says how it was verified.
"Verified" means checked on 2026-10-28 by the named test or tool; nothing is marked done on inspection alone.

## Identity and design system

| Requirement | Status | Evidence |
|---|---|---|
| Distinct identity, not navy/neon/purple-gradient | Done | Warm paper, graphite ink, ultramarine signal; see DESIGN.md. Screenshots reviewed at 1440px and 390px, light and dark. |
| Brand personality, colours, neutrals, semantic risk colours, typography, iconography, logo, illustration style, spacing, component rules | Done | DESIGN.md; tokens in `static/css/codeguard.css`; logo `templates/partials/logo.html`; illustrations `templates/illustrations/`. |
| Colours via CSS variables only, each with a defined role; risk colours meaningful and accessible | Verified | `core/tests/test_design.py`; contrast computed for every pair (≥ 4.7:1); axe `color-contrast` passes in both themes. |
| More than one font and a typographic hierarchy | Done | Newsreader (display), Instrument Sans (UI), JetBrains Mono (data); type scale in DESIGN.md. |

## Information architecture and shell

| Requirement | Status | Evidence |
|---|---|---|
| Separate pages: Overview, Supply chain, Threat library, Simulations, Results, Risk analysis, Security controls, Remediation, Reports, Activity and audit, Settings | Verified | `test_every_main_page_renders_for_analyst` (26 pages) plus `test_every_settings_page_renders_with_its_navigation` (10); README "Information architecture". |
| Persistent grouped sidebar with icons and active states; account menu; settings access; notifications entry; responsive navigation; consistent page header; breadcrumbs, tabs | Verified | `test_active_navigation_is_marked`, `test_account_menu*`; axe and keyboard audit on 47 pages; off-canvas sidebar below 992px. |
| Pages designed for their own purpose (tables, panels, diagrams, timeline, stepper, documents) | Done | Threat library = management table; supply chain = stage chain + graph; configuration = 4-step stepper; results = tabbed workspace; reports = archive + printable document; audit = timeline and table. |

## Imagery and visualisation

| Requirement | Status | Evidence |
|---|---|---|
| Original illustrations, no stock imagery, no broken external images | Done | Inline SVG only (hero, auth lattice, empty states, error page, step diagrams). The only external assets are Google Fonts, as before. |
| Supply chain and dependency visualisations | Done | Stage chain on Overview and Supply chain; aggregated propagation graph; per-run propagation diagram. |
| Charts with meaningful descriptions | Verified | Inline SVG charts have `role="img"`, a description with the numbers, focusable marks with tooltips and a table view; `test_report_page_names_diagram_tables_and_charts`. |

## Landing page

| Requirement | Status | Evidence |
|---|---|---|
| Hero, positioning, product visual, capabilities, the problem, workflow, how simulations work, sign-in entry, footer | Done | `templates/core/landing.html`; `test_landing_page_is_public`. |
| Copy describes only implemented capabilities; no exaggerated claims | Done | Every capability listed maps to a shipped feature; figures on the page are live database counts. |

## Settings

| Requirement | Status | Evidence |
|---|---|---|
| Settings navigation with separate pages | Verified | `test_every_settings_page_renders_with_its_navigation`. |
| Profile, account, appearance, theme, display, font size and typography, accessibility, notifications, privacy, security, sessions | Verified | `accounts/tests/test_settings.py` (each persists and changes behaviour). |
| Organization settings and user/role management where permitted | Verified | `test_administration_pages_are_admin_only`; live authorization matrix. Organization policies are shown read-only because they are environment variables. |
| No fake settings | Done | Every field is read by CSS tokens, a view, the notification feed or the session middleware. Email notifications are not offered because only password-reset email is implemented; the page says so. |

## Functionality preserved

| Requirement | Status | Evidence |
|---|---|---|
| Authentication, authorization, threat management, simulation engine, risk calculations, controls, reports, audit trail, models, tests | Verified | 332 tests pass (the original 268 kept, updated only where URLs or markup moved); engine untouched; live authorization matrix passed; keyboard journey 14/14. |
| No hardcoded numbers, no fabricated scenarios or outcomes | Verified | Overview, supply chain, risk analysis and notifications are computed from the database (`test_dashboard_metrics_reflect_database`, `test_supply_chain_map_counts_visible_paths_and_runs`, `test_risk_analysis_aggregates_and_scopes`, `test_notifications_from_real_records`). |
| Security checks kept | Verified | CSP unchanged (no inline scripts or styles added); theme switch is a CSRF-protected POST with an open-redirect guard; new pages enforce login and visibility; `check --deploy` unchanged. |
| Jenkins integration | Partly verified | Ruff, tests, coverage and `makemigrations --check` (the Jenkinsfile's gates) pass locally. The Jenkinsfile rehearsal was **not** re-run this round, and the pipeline has still never run on a Jenkins server. |

## Responsive and accessible

| Requirement | Status | Evidence |
|---|---|---|
| Desktop, laptop, tablet, mobile | Verified | Reflow check at 390px on 47 pages; screenshots at 1440px and 390px. Tablet widths covered by the 992px/1100px breakpoints but not separately screenshotted. |
| Keyboard, semantics, visible focus, labels, contrast, descriptions | Verified | axe-core 0 violations (47 pages × 2 widths × 2 themes); focus visible on every tab stop; error states 5/5. |
| Screen-reader testing | **Not done** | Automated checks do not replace NVDA, JAWS or VoiceOver testing. |
