# Glossary

Terms as CodeGuard uses them, with the code location that defines each. General terms are
defined only as far as this project needs them.

| Term | Meaning in CodeGuard | Defined in |
|---|---|---|
| **Accessible run** | A run the user owns, or a completed run someone shared | `simulation.services.accessible_runs` |
| **Admin / Analyst / Viewer** | The three roles. Admin manages shared scenarios, users and sees all audit events; analyst creates private scenarios and runs simulations; viewer reads | `accounts.models.Role`, `accounts.permissions` |
| **Applicable control** | A control linked to a scenario through `ScenarioControl`; highlighted on the form and preferred when ranking recommendations | `threats.models.ScenarioControl` |
| **Append-only** | Audit events cannot be updated or deleted through the ORM; only the retention command removes them | `audit.models.AppendOnlyQuerySet` |
| **Audit event** | A record of a security-relevant action with actor, object, sanitised metadata and IP | `audit.models.AuditEvent` |
| **Below threshold** | Edge outcome: base probability was already below the threshold | `propagation.OUTCOME_BELOW_THRESHOLD` |
| **Blocked (by controls)** | Edge outcome: the edge would have propagated without preventive controls. A stage with such an incoming edge and no successful one is in state `blocked` | `propagation.OUTCOME_BLOCKED`, `STATE_BLOCKED` |
| **Bypass edge** | An edge that skips at least one later stage (e.g. IDE → CI/CD) | `propagation.edge_kind` |
| **Classification / band** | low (< 15), moderate (≥ 15), high (≥ 30), critical (≥ 50) | `risk.RISK_BANDS`, `risk.classify` |
| **Combined effectiveness / coverage** | 100 × (1 − ∏(1 − εᵢ/100)) over the controls of one mode protecting a stage | `risk.combined_effectiveness` |
| **Compromised** | Stage state: reached by a propagated edge (or the entry stage) | `propagation.COMPROMISED_STATES` |
| **Contribution** | Residual risk removed by one enabled control, measured by re-running without it (leave-one-out) | `recommendations.control_contributions` |
| **Control** | A security measure in the catalogue with category, effectiveness, effort, priority, protected stages, basis and limitations | `threats.models.SecurityControl`, `domain.Control` |
| **CSP** | Content-Security-Policy response header restricting where scripts, styles, fonts and images may come from | `core.middleware.ContentSecurityPolicyMiddleware` |
| **CSRF** | Cross-site request forgery; Django's token check on unsafe requests | `CsrfViewMiddleware`, `CSRF_FAILURE_VIEW` |
| **Detective / recovery control** | A control in **mitigate** mode: lowers residual risk of a reached stage, never stops propagation | `domain.CATEGORY_MODES` |
| **Effective probability** | Edge probability after the target's preventive coverage: p × (1 − P/100) | `propagation.traverse` |
| **Entry stage** | Where the scenario's attack starts; compromised by assumption | `ThreatScenario.initial_stage` |
| **Exposed** | Stage state: attempted, not compromised, not blocked | `propagation.STATE_EXPOSED` |
| **Forward edge** | An edge to the next position | `propagation.edge_kind` |
| **IDOR** | Insecure direct object reference: reading another user's object by guessing its ID; prevented by scoped querysets returning 404 | services modules |
| **Inherent risk** | Risk computed with no controls at all | `engine.simulate` (first pass) |
| **Input snapshot** | Versioned JSON copy of everything a run used, enough to reproduce it | `simulation.services.scenario_snapshot` |
| **Likelihood (stage)** | Probability (0–100) that a stage is compromised: best successful path for compromised stages, strongest failed attempt otherwise | `propagation._path_likelihoods`, `traverse` |
| **Migration** | A versioned file of schema/data changes applied by `manage.py migrate` | `*/migrations/` |
| **Mitigating coverage (M)** | Combined effectiveness of detective and recovery controls on a stage | `engine._coverage_by_stage` |
| **Model version** | `"1.0"`, stored in every snapshot | `engine.MODEL_VERSION` |
| **Overall risk** | Weighted average of the five stage risks with stage weights | `risk.weighted_overall` |
| **Preventive control** | A control in **prevent** mode: reduces the probability of entering the stages it protects | `domain.MODE_PREVENT` |
| **Preventive coverage (P)** | Combined effectiveness of preventive controls on a stage | `engine._coverage_by_stage` |
| **Propagation event** | One evaluated edge stored for a run | `simulation.models.PropagationEvent` |
| **Propagation rule** | A scenario's directed edge source → target with a probability | `threats.models.PropagationRule` |
| **Propagation threshold (τ)** | An edge propagates when its effective probability ≥ τ (default 50) | `ThreatScenario.propagation_threshold` |
| **Raw risk** | likelihood × (severity/5) × (impact/5) | `risk.raw_risk` |
| **Recommendation** | A disabled control ranked by the modelled residual-risk reduction from re-running with it | `recommendations.recommend` |
| **Remediation item** | A recommendation an analyst committed to, with status, due date and note | `remediation.models.RemediationItem` |
| **Request ID** | Identifier attached to a request, returned as `X-Request-ID` and written in log lines | `core.observability` |
| **Residual risk** | Risk with the enabled controls applied (prevent in propagation, mitigate on the result) | `engine.simulate` (second pass) |
| **Reverse edge** | An edge to an earlier position (e.g. Registry → IDE) | `propagation.edge_kind` |
| **Run** | One execution of the engine with stored inputs and outputs; status pending, completed or failed | `simulation.models.SimulationRun` |
| **Scenario** | A hypothetical attack: entry stage, base likelihood, severity, impact, threshold, rules; shared or private, active or archived, system or custom, versioned | `threats.models.ThreatScenario` |
| **Seed** | Idempotent loading of stages, controls and system scenarios | `seed_codeguard` |
| **Session epoch** | Counter compared with the session's stored copy; incrementing it signs out other sessions | `UserPreference.session_epoch`, `SessionEpochMiddleware` |
| **Severity / impact** | Ordinal 1–5 scenario parameters scaling raw risk | `ThreatScenario` |
| **Shared** | For scenarios: visible to every user. For runs: completed and visible read-only to every user | `Visibility.SHARED`, `SimulationRun.is_shared` |
| **Stage** | One of the five supply-chain nodes, with position, weight and assets | `threats.models.SupplyChainStage` |
| **Supply-chain stages (the five)** | IDE / Developer Environment, Version Control, CI/CD Pipeline, Software Registry, Production | `threats/seed_data.STAGES` |
| **System scenario** | One of the six seeded scenarios; can be archived, never deleted | `ThreatScenario.is_system` |
| **Throttling** | Refusing sign-in after too many recent failures per username or IP | `accounts.throttling` |
| **Transmitted likelihood** | likelihood(source) × effective probability / 100 for an evaluated edge | `propagation.traverse` |
| **Unaffected** | Stage state: no edge into it was evaluated | `propagation.STATE_UNAFFECTED` |
| **Verification (remediation)** | The owner's later completed run of the same scenario with the control enabled | `remediation.services.verification` |
| **WAL** | SQLite write-ahead logging, letting readers continue during a write | `DATABASES` options |
| **Weight** | Stage criticality (1–5) used in the overall average; seeded 1, 2, 2, 2, 3 | `SupplyChainStage.weight` |
