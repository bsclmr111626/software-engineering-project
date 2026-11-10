# Learning guide

A study path through CodeGuard for someone who knows basic Python and wants to understand both
Django and this project well enough to explain, change and defend it. Each stage names the files
to read, the idea to take away and a hands-on exercise. Exercises that modify code are for a
scratch branch; none of them describe features CodeGuard has.

Commands assume the project root and, on this machine, `.venv\Scripts\python.exe` in place of
`python`.

## Stage 1 — Run it and look around (1 hour)

**Do:** follow the README Quick start, sign in as `demo_analyst`, run the seeded "Compromised
Developer Account" scenario twice: once with no controls and once with MFA, protected branches
and SCA. Open each result tab and the report document.

**Take away:** the vocabulary of the product: stage, scenario, rule, control, run, inherent vs
residual risk, blocked vs exposed. Check them against [GLOSSARY.md](GLOSSARY.md).

**Check yourself:** why is the second run's residual risk 3.3 and not 0? (Answer in
`SIMULATION_AND_RISK_METHODOLOGY.md` §3: blocked and exposed stages keep the likelihood of the
failed attempt.)

## Stage 2 — How Django turns a URL into a page (2 hours)

**Read:** `codeguard/urls.py` → `core/urls.py` → `core/views.py:landing` →
`templates/core/landing.html` → `templates/layouts/public.html` → `templates/base.html`.

**Concepts:**

* *URLconf*: `path("", include("core.urls"))` hands the rest of the path to an app; `app_name`
  creates the namespace used in `reverse("core:landing")` and `{% url %}`.
* *Function-based view*: a function that takes `request` and returns an `HttpResponse`, here via
  `render(request, template, context)`.
* *Template inheritance*: `{% extends %}` and `{% block %}`; context processors
  (`TEMPLATES[...]["context_processors"]`) add variables to every template —
  `accounts.context_processors.role` and `core.context_processors.shell`.
* *Static files*: `{% static %}` and `STATICFILES_DIRS = [BASE_DIR / "static"]`.

**Exercise:** open `/healthz/` and read `core.views.healthz`. Why is it decorated with
`require_GET` and `never_cache`, and why is it listed in `SECURE_REDIRECT_EXEMPT`?

## Stage 3 — Models, the ORM and migrations (3 hours)

**Read:** `threats/models.py`, then `DATABASE_AND_MIGRATIONS.md` in full.

**Concepts:** fields and validators; `ForeignKey` with `on_delete` (`CASCADE`, `PROTECT`,
`SET_NULL`); `ManyToManyField` with and without `through`; `TextChoices`; `Meta.ordering`,
`indexes`, `constraints`; querysets are lazy; `select_related` vs `prefetch_related`.

**Exercises:**

1. `python manage.py shell`, then:

   ```python
   from threats.models import ThreatScenario
   s = ThreatScenario.objects.get(slug="malicious-dependency")
   [(r.source.key, r.target.key, r.probability, r.kind) for r in s.rules.select_related("source", "target")]
   ```

   Which edge kinds appear, and which edge makes a cycle?
2. Point `DJANGO_DB_PATH` at a scratch file, run `migrate`, then `migrate accounts 0005` and
   `migrate accounts` again. Read `accounts/migrations/0006_retire_neutral_surface.py` and
   explain why it uses `apps.get_model`.
3. Run `python manage.py sqlmigrate threats 0003` and explain the four SQL statements per field.

## Stage 4 — Forms and validation in layers (2 hours)

**Read:** `simulation/forms.py`, `threats/forms.py` (`BasePropagationRuleFormSet.clean`),
`simulation/engine.py:validate_input`, the `CheckConstraint`s in `threats/models.py`.

**Concept:** CodeGuard validates the same rule up to three times: in the form (friendly message),
in the engine (`SimulationConfigError`, independent of the web layer), and in the schema (last
line of defence). Find the three places that stop a self-loop rule.

**Exercise:** in a test, post a rule formset whose only rule starts at a stage that is not the
scenario's entry stage. Which message appears, and which part of `clean()` produced it?

## Stage 5 — The engine (4 hours, the core of the project)

**Read in this order:** `simulation/domain.py`, `simulation/risk.py`,
`simulation/propagation.py`, `simulation/engine.py`, `simulation/recommendations.py`, then
`SIMULATION_AND_RISK_METHODOLOGY.md`.

**Concepts:** frozen dataclasses as value objects; pure functions; breadth-first search with a
queue (`collections.deque`); a max-product variant of Dijkstra with `heapq`; deterministic
ordering; leave-one-out analysis; why rounding is done with `Decimal` and why threshold
comparisons are rounded to six places.

**Exercises** (no database needed):

```python
from simulation.tests.factories import make_input
from simulation.engine import simulate
r = simulate(make_input(likelihood=80, threshold=50))
[(s.key, s.state, s.residual_likelihood, s.residual_risk) for s in r.stages], r.residual_risk
```

1. Every edge in `make_input` is 80 %. Predict the likelihood of each stage before running it
   (80, 64, 51.2, 40.96, 32.768), then check.
2. Set `threshold=81`. Predict the states.
3. Recompute by hand the worked example in the methodology document, then reproduce it in the
   shell with `services.build_input` against a seeded scratch database.
4. Read `test_most_likely_path_is_used` and design a graph where the most likely path is longer
   than the shortest one.

## Stage 6 — Services, transactions and persistence (2 hours)

**Read:** `simulation/services.py` (`run_simulation`, `_execute`, `accessible_runs`),
`simulation/serialization.py`, `simulation/models.py`.

**Concepts:** keeping views thin; `transaction.atomic`; why the run row is created *before* the
atomic block (so a failure can still be recorded as `failed`); `bulk_create`; JSON snapshots and
`snapshot_version`; reproducibility.

**Exercise:** read `test_failure_marks_run_failed_without_partial_results`. How does it force a
failure, and what does it assert about stage results and events?

## Stage 7 — Authentication, authorization and middleware (3 hours)

**Read:** `accounts/permissions.py`, `accounts/forms.py`, `accounts/throttling.py`,
`accounts/signals.py`, `accounts/middleware.py`, `core/middleware.py`,
`core/observability.py`, `codeguard/settings.py` (security section), then `SECURITY.md`.

**Concepts:** decorators that wrap views (`role_required` builds `admin_required` and
`analyst_required`); object-level access through scoped querysets; returning 404 instead of 403
to avoid disclosure; Django signals (`post_save`, `user_logged_in`, `user_login_failed`);
middleware as a chain of callables; CSP with a script hash; context variables for request IDs.

**Exercises:**

1. Draw the role matrix from the decorators alone, then compare with `SECURITY.md` §3.1.
2. Explain why the throttle check happens in `clean()` *before* `super().clean()`.
3. Explain the proxy problem with `client_ip` (`SECURITY.md` §1).

## Stage 8 — Presentation: templates, charts and the design system (2 hours)

**Read:** `DESIGN.md`, `static/css/codeguard.css` (token block), `core/theme.py`,
`simulation/charts.py`, `simulation/visual.py`, `core/svgcharts.py`, `static/js/app.js`.

**Concepts:** design tokens as CSS variables; preferences rendered as `data-*` attributes; why
the theme script must run before CSS applies, and how the CSP hash is computed from the same
constant; Matplotlib's object-oriented API on a server; computing SVG geometry in Python and
keeping templates dumb; progressive enhancement.

**Exercise:** request `/simulations/<id>/chart/stages.png?palette=garbage` and explain the
result from `parse_palette`.

## Stage 9 — Testing and CI (2 hours)

**Read:** `pytest.ini`, `conftest.py`, `codeguard/test_settings.py`, one file from each layer
(`test_risk.py`, `test_services_and_views.py`, `tests/test_integration.py`,
`core/tests/test_design.py`), `Jenkinsfile`, `.github/workflows/ci.yml`,
`scripts/rehearse_jenkinsfile.py`, then `TESTING_AND_QUALITY_ASSURANCE.md`.

**Exercises:**

1. Run `pytest --cov` and find the one uncovered line in `simulation/engine.py` (line 99,
   reported on 2026-11-10). What would a test for it look like?
2. Check out `8f5d092` in a temporary clone and run the tests there. Explain the 9 failures
   from `.gitignore` alone, then compare with `eef6716`.
3. Explain the difference between "the Jenkinsfile was rehearsed" and "the pipeline ran on
   Jenkins".

## Stage 10 — Explain it to someone else

Prepare a ten-minute walkthrough that covers: the five stages and why they are ordered; one
simulation from form to chart (use [simulation-workflow](diagrams/simulation-workflow.md)); the
formula with the worked example; two security controls with their tests; two limitations you
would fix first and how. Good candidates from this documentation: MFA for CodeGuard accounts, a trusted-proxy setting for `client_ip`, an uncertainty
range for the model.

## Self-test questions (answers are in the linked documents)

1. What makes an edge "blocked" rather than "below threshold"? (methodology §2.2)
2. Why can a report survive deletion of its scenario? (data-flow diagram; `SimulationRun` docstring)
3. Which migration contains Python code, and what happens when you reverse it? (DB §2.6)
4. Who can see a private report, and what response does anyone else get? (security §3.2)
5. Why is `pyplot` not used? (architecture §3)
6. Which controls mitigate rather than prevent? (`domain.CATEGORY_MODES`; seed: `sca`,
   `runtime-monitoring`, `incident-response`)
7. What does `--strict-markers` protect against? (testing §3)
8. What exactly is unverified about the Jenkins pipeline? (deployment §4)
