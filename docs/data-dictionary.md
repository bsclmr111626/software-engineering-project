# CodeGuard — Data Dictionary

Field types are Django field types stored in SQLite. "PK" is the primary key and "FK" a foreign key. Unless stated otherwise, percentages are integers from 0 to 100 and levels are integers from 1 to 5.

## accounts.Profile — a user's CodeGuard role

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| id | BigAutoField | PK | |
| user | OneToOne → auth.User | CASCADE, unique | Owner of the profile |
| role | Char(16) | `admin` / `analyst` / `viewer`, CHECK `profile_role_valid` | Server-assigned role. Superusers are always treated as admin. |
| created_at / updated_at | DateTime | auto | Timestamps |

## threats.SupplyChainStage — a node of the supply chain graph

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| key | Slug(32) | unique | Stable identifier (`ide`, `vcs`, `cicd`, `registry`, `production`) |
| name | Char(80) | | Display name |
| position | PositiveSmallInt | unique | Order in the chain (1–5) |
| description | Text | | Role of the stage |
| assets | Text | | Typical assets at the stage |
| icon | Char(40) | | Bootstrap Icons name |
| weight | PositiveSmallInt | 1–5, CHECK `stage_weight_range` | Criticality weight for the overall-risk average |

## threats.SecurityControl — the reusable mitigation catalog

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| slug | Slug(64) | unique | Stable identifier |
| name, description | Char / Text | | |
| category | Char(16) | `preventive` / `detective` / `recovery` | Preventive controls reduce propagation; detective and recovery controls reduce stage risk |
| stages | M2M → SupplyChainStage | | Stages the control protects |
| effectiveness | PositiveSmallInt | 0–100, CHECK | Illustrative model parameter |
| effort, priority | Char(8) | `low` / `medium` / `high` | Implementation effort and priority |
| addresses | Text | | Weakness or path the control addresses |
| effectiveness_basis | Text | | The assumption behind the effectiveness value (illustrative, not measured) |
| limitations | Text | | What the control does not cover or can be bypassed by |

## threats.ThreatScenario — a hypothetical attack (simulation input)

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| slug | Slug(80) | unique | URL identifier, generated with a random suffix on collision |
| name, description | Char(120) / Text | | |
| initial_stage | FK → SupplyChainStage | PROTECT | Attack entry point |
| likelihood | PositiveSmallInt | 0–100, CHECK | Base likelihood of the initial compromise |
| severity, impact | PositiveSmallInt | 1–5, CHECK | Technical severity and business impact |
| propagation_threshold | PositiveSmallInt | 1–100, CHECK, default 50 | Edge decision threshold |
| business_impact, asset_categories, assumptions, preventive_measures, detective_measures | Text / Char | | Explanatory content |
| owner | FK → User | nullable, CASCADE | Owner (null for system scenarios) |
| visibility | Char(8) | `shared` / `private`; CHECK `private_scenario_has_owner` | Who can see the scenario |
| status | Char(8) | `active` / `archived` | Archived scenarios cannot be simulated |
| is_system | Boolean | | Seeded; protected from deletion |
| version | PositiveInt | default 1, +1 on each edit | Recorded in run snapshots |
| controls | M2M → SecurityControl through ScenarioControl | | Controls relevant to the scenario |
| created_at / updated_at | DateTime | auto | |

Index: `(status, visibility)`.

## threats.PropagationRule — a directed edge for one scenario

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| scenario | FK → ThreatScenario | CASCADE | |
| source, target | FK → SupplyChainStage | PROTECT; CHECK source ≠ target; UNIQUE (scenario, source, target) | Edge endpoints |
| probability | PositiveSmallInt | 0–100, CHECK | Chance the compromise crosses the edge |
| rationale | Char(255) | | Why the edge exists |
| *kind* (property) | — | derived | `forward` (next stage), `bypass` (skips stages) or `reverse` (backwards) |

## threats.ScenarioControl — links a scenario to its relevant controls

| Field | Type | Constraints |
|---|---|---|
| scenario | FK → ThreatScenario | CASCADE |
| control | FK → SecurityControl | PROTECT; UNIQUE (scenario, control) |
| note | Char(255) | optional |

## simulation.SimulationRun — one execution of the engine

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| id | UUID | PK (uuid4) | Unguessable run identifier |
| user | FK → User | CASCADE | Owner |
| scenario | FK → ThreatScenario | nullable, SET_NULL | Live link (null after the scenario is deleted) |
| scenario_name, scenario_slug, scenario_version, entry_stage_name | Char / Slug / Int | | Denormalised for history |
| status | Char(10) | `pending` / `completed` / `failed`, indexed | Lifecycle state |
| error_message | Char(255) | | Generic message only (details go to the server log) |
| is_shared | Boolean | | Read-only visibility for all users |
| likelihood, severity, impact, threshold | PositiveSmallInt | | Inputs actually used |
| enabled_controls | JSON list | | Control slugs |
| inherent_risk, residual_risk | Float | nullable; CHECK residual 0–100 | Overall scores |
| classification | Char(16) | | `low` / `moderate` / `high` / `critical` |
| compromised_count, blocked_count | PositiveSmallInt | | Summary counts |
| input_snapshot | JSON | | Versioned snapshot: scenario, rules, stages, controls, `snapshot_version` (2 adds `control_assumptions`: basis and limitations of each enabled control), `model_version` |
| result | JSON | | Full engine output, including recommendations, contributions, explanation and limitations |
| created_at, completed_at | DateTime | indexed | |

Indexes: `(user, -created_at)` and `(is_shared, status)`.

## simulation.SimulationStageResult — the outcome for one stage in a run

| Field | Type | Meaning |
|---|---|---|
| run | FK → SimulationRun (CASCADE) | UNIQUE (run, stage_key) |
| stage_key, stage_name, position | Slug / Char / Int | Denormalised stage identity |
| state, inherent_state | Char(16) | `entry` / `compromised` / `blocked` / `exposed` / `unaffected`, with and without controls |
| inherent_likelihood, residual_likelihood | Float | 0–100 |
| preventive_coverage, mitigating_coverage | Float | Combined coverage, 0–100 |
| inherent_risk, residual_risk | Float | 0–100 |
| classification | Char(16) | Risk class of the residual risk |
| explanation | Text | Plain-language reasoning |

Index: `(stage_key, state)`, used by the dashboard.

## simulation.PropagationEvent — one evaluated edge in a run

| Field | Type | Meaning |
|---|---|---|
| run | FK (CASCADE) | UNIQUE (run, order) |
| order | PositiveSmallInt | Evaluation order (BFS) |
| source_key/name, target_key/name | Slug / Char | Denormalised endpoints |
| kind | Char(16) | `forward` / `bypass` / `reverse` |
| base_probability, control_coverage, effective_probability, threshold | Float | Decision inputs |
| outcome | Char(24) | `propagated` / `blocked_by_controls` / `below_threshold` |
| target_already_compromised | Boolean | True when a cycle reached an already compromised stage |
| transmitted_likelihood | Float | Likelihood carried across the edge |
| controls_applied | JSON list | Preventive controls on the target |
| explanation | Char(300) | Plain-language reasoning |

## audit.AuditEvent — append-only record of important actions

| Field | Type | Meaning |
|---|---|---|
| actor | FK → User, nullable, SET_NULL | Who acted (null for anonymous or deleted users) |
| actor_username | Char(150) | Username snapshot |
| action | Char(32), indexed | See `AuditAction` (login, register, scenario_*, simulation_*, report_*, role_change, …) |
| object_type, object_id, object_repr | Char | Target reference |
| metadata | JSON | Sanitised context; never contains passwords, tokens or session data |
| ip_address | GenericIPAddress | From `REMOTE_ADDR` |
| created_at | DateTime, indexed | |

Index: `(actor, -created_at)`. `save()` refuses updates, and `delete()` plus the QuerySet's bulk `update()`/`delete()` raise, so events can only be appended. Old events are removed only by `manage.py purge_audit_events --days N` (N ≥ 30), which records an `audit_purge` event.

## remediation.RemediationItem — a recommended control someone has committed to

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| owner | FK → User | CASCADE | The analyst who tracks the item; items are private to their owner |
| control | FK → SecurityControl | PROTECT | The control to adopt |
| scenario | FK → ThreatScenario | nullable, SET_NULL | Live link |
| scenario_slug, scenario_name | Slug / Char | | Denormalised so the item survives scenario deletion |
| source_run | FK → SimulationRun | nullable, SET_NULL | The report the recommendation came from |
| baseline_risk | Float | | Overall residual risk of the source run |
| expected_reduction | Float | CHECK ≥ 0 | Modeled reduction when the item was created |
| status | Char(16) | `open` / `in_progress` / `done` / `risk_accepted` | |
| note | Text (≤ 2000) | | Owner, ticket reference or decision rationale |
| due_date | Date | nullable | |
| created_at, updated_at, closed_at | DateTime | | `closed_at` is set on entering done/risk accepted and cleared on reopening |

Constraints: at most one *open or in-progress* item per (owner, scenario_slug, control) (conditional UNIQUE). Index: `(owner, status)`. Verification is not stored: it is the owner's latest later completed run of the same scenario with the control enabled.
