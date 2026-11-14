# Architecture

CodeGuard is a **server-rendered Django monolith**: one deployable unit, six project apps, one
SQLite database, no JavaScript build step and no third-party request from the browser (fonts,
icons and Bootstrap are vendored). The one optional external service is the email provider. Diagrams: [architecture](diagrams/architecture.md),
[request lifecycle](diagrams/request-lifecycle.md), [data flow](diagrams/data-flow.md).

## 1. Layers

| Layer | What lives there | Rule |
|---|---|---|
| Presentation | `templates/` (Django templates), `static/css/codeguard.css`, `static/js/app.js`, vendored Bootstrap | Templates only display; geometry for diagrams is computed in Python (`simulation/visual.py`, `core/svgcharts.py`) |
| Views | `*/views.py`, `accounts/settings_views.py` | Function-based views. Authentication and role decorators on every protected view; no business rules beyond input parsing |
| Services | `simulation/services.py`, `threats/services.py`, `remediation/services.py`, `core/services.py`, `core/analytics.py`, `core/notifications.py`, `audit/services.py` | Visibility rules, transactions, persistence, aggregation |
| Domain engine | `simulation/domain.py`, `engine.py`, `propagation.py`, `risk.py`, `recommendations.py`, `serialization.py` | Pure Python; imports no Django module; never touches the database |
| Persistence | `*/models.py`, `*/migrations/` | Django ORM, constraints in the schema |

The direction of dependencies is strictly downward. The one upward-looking import is
`threats/models.py` importing `simulation.propagation.edge_kind`, a pure function used for the
`PropagationRule.kind` property.

## 2. The apps

| App | Responsibility | Main files |
|---|---|---|
| `accounts` | Roles (`Profile`), registration policy, sign-in throttling, session revocation, every Settings page, user preferences, deploy check `codeguard.W001` | `models.py`, `permissions.py`, `throttling.py`, `middleware.py`, `signals.py`, `preferences.py`, `settings_views.py`, `checks.py` |
| `audit` | Append-only `AuditEvent`, `record_event`, the audit log page, retention command | `models.py`, `services.py`, `views.py`, `management/commands/purge_audit_events.py` |
| `threats` | Stage catalogue, control catalogue, scenarios and propagation rules; seed data | `models.py`, `forms.py` (graph validation), `services.py`, `seed_data.py`, `management/commands/seed_codeguard.py` |
| `simulation` | Engine, run persistence, result/report views, Matplotlib charts, CSV exports, comparisons | see the Domain row above, plus `services.py`, `views.py`, `charts.py`, `exports.py`, `visual.py`, `report_urls.py` |
| `remediation` | Remediation plan created from recommendations; verification by later runs | `models.py`, `services.py`, `views.py` |
| `core` | Landing page, overview dashboard, supply-chain map, risk analysis, help/methodology, notifications, health check, error pages, CSP and request-ID middleware, theme script, template tags, backup command | `views.py`, `services.py`, `analytics.py`, `notifications.py`, `middleware.py`, `observability.py`, `theme.py`, `svgcharts.py`, `templatetags/codeguard_tags.py` |

`core` has no models. The Reports area (`/reports/`) is not an app: its URLs live in
`simulation/report_urls.py` and its views in `simulation/views.py` because they read simulation
models.

## 3. Key design decisions (with the reason found in the code)

1. **Engine separated from Django.** `simulation/domain.py`: "These classes deliberately have no
   Django dependency… guarantees that a simulation cannot accidentally read or write the
   database." It makes the 85 engine and risk tests fast and database-free
   (`simulation/tests/factories.py`).
2. **Stored snapshots, not live joins, for history.** `SimulationRun` stores `input_snapshot`
   and `result` JSON plus denormalised scenario name/slug/version, and stage results/events
   store stage names as text. Docstring: "editing or deleting the scenario later never changes a
   historical report."
3. **Charts rendered on the server.** `simulation/charts.py` uses Matplotlib's object-oriented
   API (`Figure` + `FigureCanvasAgg`) rather than `pyplot`, because it "keeps no global state, is
   safe in a multi-threaded server". PNGs are produced in memory and returned by
   access-controlled views, so no chart file or path ever exists.
4. **Synchronous runs.** A simulation runs inside the POST request. The engine runs once for the
   result plus once per recommendation candidate and once per enabled control, all in
   milliseconds; `docs/engineering-assessment.md` L1 records this as accepted.
5. **SQLite tuned for several workers.** `DATABASES["default"]["OPTIONS"]`: WAL journal,
   `transaction_mode: IMMEDIATE`, 20 s busy timeout, `synchronous=NORMAL`, foreign keys on.
6. **Single-tenant deployment.** "Shared" means every account on the instance; registration
   policy (`CODEGUARD_REGISTRATION`) is the tenancy control (assessment H2).
7. **Progressive enhancement.** `static/js/app.js` header: "Every feature also works without JS
   except the 'add rule' helper…, the account menu… and chart tooltips."

## 4. Frontend

* **Templates.** `templates/base.html` loads the CSS, the vendored Bootstrap bundle and
  `static/js/app.js`, and renders the pre-paint theme script via the `theme_init_script` tag.
  Layouts: `layouts/public.html`, `auth.html`, `app.html`, `settings.html`. Reusable pieces in
  `components/` (pipeline SVG, legend, pagination, messages, form field, status), `partials/` and
  inline SVG illustrations in `illustrations/`.
* **Design system.** `DESIGN.md` defines the tokens; colours exist only between `@tokens:start`
  and `@tokens:end` in `static/css/codeguard.css`. `core/tests/test_design.py` enforces the rules
  (no colour literals in templates or JS, no theme branching, both themes define the same tokens).
* **Preferences reach the CSS** as `data-*` attributes on `<html>` (`accounts.preferences.html_attributes`:
  `data-theme-pref`, `data-accent`, `data-surface`, `data-text-size`, `data-heading-font`,
  `data-density`, and optional `data-motion`, `data-contrast`, `data-links`).
* **Charts follow the theme.** `app.js renderCharts()` reads nine CSS variables
  (`PALETTE_TOKENS` order: surface, text, text-muted, border, border-strong, sev-low, sev-med,
  sev-high, sev-crit) and rewrites each chart `<img>` URL with `?palette=`; `charts.parse_palette`
  falls back to the light palette for anything malformed.
* **Two chart technologies.** Matplotlib PNGs on run pages, comparison and the dashboard
  distribution (`/overview/risk-distribution.png`); SVG geometry computed in Python
  (`core/svgcharts.hbars`, `line_chart`, `paired_columns`) on the overview and risk-analysis pages
  and the five-stage pipeline (`simulation/visual.build_pipeline`, drawn by
  `components/pipeline.html`). Charts have text/table alternatives (README "Accessibility").

## 5. End-to-end trace: opening a stored result and its chart

This complements the form-to-engine trace in
[simulation-workflow](diagrams/simulation-workflow.md).

1. `GET /simulations/<uuid>/stages/` resolves to `simulation.views.detail(request, run_id,
   section="stages")`; an unknown section raises 404.
2. `services.get_accessible_run(user, run_id)` filters
   `Q(user=user) | Q(is_shared=True, status=COMPLETED)`; a miss (or a malformed UUID) is 404, so
   the existence of other users' private runs is not disclosed.
3. `_result_context` loads `stage_results` and `events` (ordered by position / order), counts
   outcomes for the chart's text alternative, finds the owner's previous completed run of the
   same scenario, builds the pipeline geometry from stored rows, adds unevaluated rules from the
   snapshot as "Not evaluated", reads `limitations` from the stored result, flags
   `scenario_changed` when the scenario's version moved on, and looks up the user's tracked
   remediation items.
4. The template emits `<img src="…/chart/stages.png" data-chart-palette=…>`; `app.js` swaps in
   the current theme palette.
5. `simulation.views.chart` re-checks access, refuses incomplete runs, calls
   `charts.stage_risk_chart(list(run.stage_results.all()), palette)` and returns
   `image/png` with `Cache-Control: private, max-age=300`.

## 6. Cross-cutting concerns

| Concern | Mechanism | File |
|---|---|---|
| Request correlation | `RequestIdMiddleware` + `RequestIdFilter`; header `X-Request-ID` | `core/observability.py` |
| Logging | stdout/stderr, text or JSON (`CODEGUARD_LOG_FORMAT`) | `codeguard/settings.py` `LOGGING` |
| Audit | `record_event()` called from views, services and auth signals | `audit/services.py` |
| Shell context | `core.context_processors.shell` (preferences, nav section, unread count) and `accounts.context_processors.role` | |
| Errors | `handler400/403/404/500` and `CSRF_FAILURE_VIEW` render friendly templates without details | `core/views.py` |
| Health | `/healthz/` runs `SELECT 1` | `core/views.healthz` |

## 7. Performance characteristics (observed from the code, not benchmarked here)

* Queries are bounded with `select_related`/`prefetch_related` on list pages; preferences are
  cached on the user object per request (`preferences_for`).
* `remediation.views.plan` calls `services.verification(item)` for every item on the page, each
  scanning up to 50 runs: an N+1 pattern that is fine for a page of 10–50 items.
* Dashboard and analytics aggregate in SQL over all accessible completed runs on every request;
  there is no caching layer.
* README records a concurrency test (4 processes × 50 runs on one SQLite file, 200/200
  completed, 2026-10-26). It was not repeated for this documentation.

## 8. Maintainability

Strengths: small modules with docstrings that explain *why*; one formula per function; enums
(`TextChoices`) for every state; constraints duplicated in forms and schema; a design-rule test
suite; Ruff with security (`S`) and Django (`DJ`) rules. Weak spots: settings views are long
(`accounts/settings_views.py`), views build context dictionaries inline, and the Reports templates
were outside version control until commit `eef6716` (see the master document, "Known gaps").
