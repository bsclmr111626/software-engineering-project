# CodeGuard — Requirements Specification

## 1. Problem statement

Modern software passes through several connected systems (developer machines, source repositories, CI/CD pipelines, package registries and production) before it reaches users. A compromise at one stage, such as a phished developer account, a malicious dependency or a leaked pipeline token, can be inherited by every later stage. Students and small teams find it hard to reason about this chain because real incidents are complex and real testing is risky and often unauthorised.

## 2. Objectives

1. Let users explore **hypothetical** supply chain attacks safely, with no interaction with real systems.
2. Make propagation and risk **explainable**: every number can be traced to a formula and an input.
3. Show the modeled effect of security controls through **before/after** comparisons.
4. Demonstrate secure software engineering practice: authentication, authorisation, validation, auditing, testing and CI.

## 3. Scope

**In scope:**

- A five-stage supply chain model.
- Seeded and custom threat scenarios.
- A deterministic simulation engine.
- Risk scoring.
- A control catalog and recommendations.
- Run history and comparison.
- Charts and a dashboard.
- Roles and an audit log.
- CSV export.
- A Jenkins pipeline.

**Out of scope:** see §9.

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Users can register with a username, email and validated password; the role is assigned by the server. Registration can be open, limited to allowed email domains, or closed (`CODEGUARD_REGISTRATION`). | Must |
| FR-02 | Users can sign in, sign out (POST), change their password and reset a forgotten password by email. | Must |
| FR-03 | All application pages except landing, methodology and auth pages require authentication. | Must |
| FR-04 | The system has three roles: Administrator, Analyst and Viewer. Permissions are enforced on the server. | Must |
| FR-05 | Administrators can change other users' roles. Users cannot change their own role, and registration cannot grant the admin role. | Must |
| FR-06 | The system models five ordered stages with key, name, position, description, assets and criticality weight. | Must |
| FR-07 | The threat library lists the scenarios visible to the user, with search, filters (entry stage, severity, status, visibility) and pagination. | Must |
| FR-08 | At least six seeded scenarios exist, each with entry stage, likelihood, severity, impact, business impact, assets, rules, controls, assumptions and preventive/detective measures. | Must |
| FR-09 | Analysts can create, edit (versioned), archive/restore, delete and clone **their own private** scenarios. Administrators can also manage shared scenarios. System scenarios cannot be deleted. | Must |
| FR-10 | Scenario propagation rules are validated: probability 0–100, no self-loops, no duplicates, and every rule reachable from the initial stage. | Must |
| FR-11 | The seed command is idempotent and never creates duplicates. | Must |
| FR-12 | Users with the Analyst or Admin role can configure a simulation (scenario, likelihood, severity, impact, threshold, enabled controls) and run it. | Must |
| FR-13 | The engine propagates a compromise through the graph using deterministic threshold rules and handles cycles safely. | Must |
| FR-14 | The engine computes inherent and residual risk per stage and overall, using the documented formulas. | Must |
| FR-15 | Results show the pipeline (entry, compromised, exposed, blocked and unaffected stages, with a legend), edge outcomes, stage scores, classification, plain-language reasoning and limitations. | Must |
| FR-16 | The system recommends controls with the weakness addressed, the stages protected, the reason, the modeled risk change and the effort. | Must |
| FR-17 | Users can rerun with different controls and compare two runs (before/after). | Must |
| FR-18 | Completed runs are stored with an immutable input snapshot. Reports do not change when a scenario is edited or deleted. | Must |
| FR-19 | Users can see their run history, reopen reports, share a report read-only and export CSV. | Must |
| FR-20 | Matplotlib charts are generated from stored results: overall inherent vs residual, risk by stage, outcome distribution, before/after comparison, and dashboard risk distribution. | Must |
| FR-21 | The dashboard shows accessible scenarios, run counts, average residual risk, high-risk runs, most exposed stages, recent activity, recommended controls and risk distribution, all from real data. | Must |
| FR-22 | The control library lists the controls with purpose, stages, effectiveness, effort and priority. | Must |
| FR-23 | Important actions are audited: login, logout, failed login, registration, password change, scenario changes, runs, sharing, exports and role changes. | Must |
| FR-24 | The audit log is visible to administrators in full; other users see only their own events. | Must |
| FR-25 | A methodology page explains stages, rules, formulas, assumptions and limitations, and shows a disclaimer. | Must |
| FR-26 | Repeated failed sign-ins are throttled per username and per client IP, and throttled attempts are audited. | Must |
| FR-27 | Each catalog control states the basis of its effectiveness value and its limitations; runs record these for the controls they used. | Should |
| FR-28 | Analysts can add a report's recommended control to a private remediation plan, set status (open, in progress, done, risk accepted), due date and notes, and see whether a later run with the control enabled verified the modeled effect. Changes are audited. | Should |
| FR-29 | Operators have a health endpoint, request-correlated (optionally JSON) logs, an online verified backup command and an audit retention command. | Should |

## 5. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Determinism | Identical inputs always produce identical results, regardless of rule order. |
| NFR-02 | Explainability | Every stage and edge result carries a human-readable explanation. |
| NFR-03 | Security | CSRF on all state changes; ORM only; output escaping; IDOR protection; strict CSP; secure cookies in production; secrets from the environment. |
| NFR-04 | Privacy | Audit metadata never contains passwords, tokens or session data. |
| NFR-05 | Integrity | A run either completes atomically or is marked FAILED with no partial results. |
| NFR-06 | Testability | The engine has no framework dependencies. Core engine coverage is at least 85%. |
| NFR-07 | Usability | Responsive layout; keyboard focus visible; labelled inputs; meaning never conveyed by colour alone; empty and error states. |
| NFR-08 | Performance | Simulating 5 stages takes milliseconds. Lists are paginated and the dashboard uses aggregate queries. |
| NFR-09 | Portability | Runs on a typical laptop with SQLite and no external services. Static assets are vendored. |
| NFR-10 | Maintainability | Business logic lives in service and engine modules, not in views or templates. Ruff lint and format are clean. |

## 6. User roles and permissions

| Capability | Viewer | Analyst | Administrator |
|---|:-:|:-:|:-:|
| View dashboard, shared scenarios, controls, methodology | ✓ | ✓ | ✓ |
| View shared reports | ✓ | ✓ | ✓ |
| Run simulations, view own reports, export CSV, share own reports | – | ✓ | ✓ |
| Create / edit / archive / delete / clone **own private** scenarios | – | ✓ | ✓ |
| Create / edit / archive **shared** scenarios | – | – | ✓ |
| Delete seeded system scenarios | – | – | – (archive only) |
| Change user roles (not their own) | – | – | ✓ |
| View the full audit log | own events | own events | all events |

## 7. Assumptions and constraints

- The scenarios are hypothetical teaching examples. The probabilities and effectiveness values are illustrative parameters.
- Only the decisions are deterministic: the threshold rule is a simplification of conditional likelihood.
- The required stack is Django, SQLite, Bootstrap 5 and Matplotlib, with a Jenkins pipeline.
- The application runs locally. Deployment is documented but not performed.

## 8. Acceptance criteria

The project is accepted when every Must requirement above is implemented and covered by an automated or manually verified test (see [test-plan.md](test-plan.md)), and the following all hold:

- The full test suite passes.
- Core coverage is at least 85%.
- Ruff and the Django checks are clean.
- The README instructions start the app from scratch.

## 9. Out of scope

- Real scanning, exploitation or integration with real CI/CD, VCS or registries.
- Statistically calibrated predictions or the use of real-world telemetry.
- A REST API, a single-page frontend, multi-tenancy or organisations (one organization per deployment; see docs/engineering-assessment.md, H2).
- PostgreSQL, Celery or Redis (the move to PostgreSQL is documented in docs/architecture.md, section 9). Production deployment is documented in docs/deployment.md but has not been carried out.
- PDF export and a probabilistic (Monte-Carlo) mode. These are possible future work.
