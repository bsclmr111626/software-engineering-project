# Simulation and risk methodology

This document states exactly what the CodeGuard engine computes, using the source as the only
authority. Every formula below is quoted from or traceable to `simulation/risk.py`,
`simulation/propagation.py`, `simulation/engine.py` and `simulation/recommendations.py`
(`MODEL_VERSION = "1.0"`). The worked example was produced by running the real engine on the
seeded data on 2026-11-10 and was then recomputed by hand.

**Status: implemented and verified.** 91 unit tests target these modules (`test_risk.py` 44,
`test_engine.py` 41, `test_recommendations.py` 6) and all pass; branch coverage of the four
modules is 99 %.

**What it is not.** The model is a deterministic teaching model. It uses no telemetry and
inspects no real system. Its probabilities and control effectiveness values are illustrative
parameters, not measurements (`engine.LIMITATIONS`, `threats/seed_data.py` header).

## 1. Inputs

The engine consumes one immutable `SimulationInput` (`simulation/domain.py`). Every field comes
from the database through `simulation.services.build_input`, or from a stored snapshot through
`input_from_snapshot`.

| Symbol | Field | Range | Source in the app |
|---|---|---|---|
| S | `stages` | ≥ 1 stage; unique `key` and `position`; integer `weight` ≥ 1 | all `SupplyChainStage` rows, ordered by `position` |
| e | `entry_stage` | a key in S | `ThreatScenario.initial_stage` |
| L₀ | `likelihood` | 0–100 | form field "Base likelihood (%)", default from the scenario |
| σ | `severity` | integer 1–5 | form field, default from the scenario |
| ι | `impact` | integer 1–5 | form field, default from the scenario |
| E | `edges` | each `Edge(source, target, probability p)` with p in 0–100; no self-loops, no duplicates, both ends in S | the scenario's `PropagationRule` rows |
| C | `controls` | each `Control(key, effectiveness ε, stages, category, …)`, ε in 0–100, keys unique, stages in S | the controls ticked on the form |
| τ | `threshold` | > 0 and ≤ 100 (form: integer 1–100) | form field, default `propagation_threshold` (50) |

`engine.validate_input` rejects anything outside these ranges with a `SimulationConfigError`
before a run row is created (`services.run_simulation` calls it first). Booleans are not
accepted as numbers (`risk._is_number`), and severity/impact must be real integers
(`validate_level`).

A control acts in one of two **modes**, decided by its category (`domain.CATEGORY_MODES`):

```python
CATEGORY_MODES = {
    "preventive": MODE_PREVENT,
    "detective": MODE_MITIGATE,
    "recovery": MODE_MITIGATE,
}
```

* **prevent**: lowers the probability that a compromise *enters* a stage the control protects;
* **mitigate**: does not change propagation, but lowers the *residual risk* of a protected stage.

## 2. Formulas

### 2.1 Combined control coverage

For each stage s and each mode m, the coverage is the combined effectiveness of all enabled
controls of that mode that list s among their stages (`engine._coverage_by_stage`,
`risk.combined_effectiveness`):

```
coverage_m(s) = 100 × (1 − ∏ (1 − εᵢ / 100))      over controls i with mode m protecting s
```

With no applicable controls the product is empty (= 1) and coverage is 0. Because each factor is
in [0, 1], coverage can approach but never exceed 100. The assumption, stated in `LIMITATIONS`,
is that controls act independently.

Write P(s) = coverage_prevent(s) and M(s) = coverage_mitigate(s).

### 2.2 Edge evaluation

For an edge u → v with probability p (`propagation.traverse`):

```
effective(u→v) = p × (1 − P(v) / 100)
```

The outcome is decided with `risk.meets_threshold`, which compares values rounded to 6 decimal
places (`DECISION_PRECISION = 6`) so that 49.9999999 cannot flip a decision:

| Condition | Outcome constant | Meaning |
|---|---|---|
| effective ≥ τ | `propagated` | the compromise spreads to v |
| effective < τ and p ≥ τ | `blocked_by_controls` | it would have spread without controls |
| p < τ | `below_threshold` | it would not have spread anyway |

The comparison is inclusive: an edge exactly at the threshold propagates
(`test_threshold_boundary_is_inclusive`).

### 2.3 Traversal order

Breadth-first from e. `compromised = {e}`. Each time a stage leaves the queue, **all** its
outgoing edges are evaluated, in order of target position. A newly compromised target is
queued; an already compromised one is recorded (`target_already_compromised=True`) but never
re-queued, so every edge is evaluated at most once and cycles terminate. Edges whose source is
never compromised are never evaluated; the pipeline diagram shows them as "Not evaluated".

### 2.4 Stage likelihood

For compromised stages, the likelihood is the most likely successful path
(`propagation._path_likelihoods`, a max-product Dijkstra variant over `propagated` edges only):

```
λ(e) = L_entry
λ(v) = max over successful paths e → … → v of  L_entry × ∏ (effective_k / 100)
```

Since each factor is ≤ 1, a longer path can never raise the value, which keeps the search well
defined on cyclic graphs. Paths are not summed (stated in `LIMITATIONS`).

Every evaluated edge then gets a **transmitted likelihood**:

```
transmitted(u→v) = λ(u) × effective(u→v) / 100
```

A stage that was attempted but not compromised keeps the likelihood of its strongest failed
attempt, its "residual exposure":

```
λ(v) = max over evaluated edges into v of transmitted(u→v)       if v is not compromised
λ(v) = 0                                                         if no edge into v was evaluated
```

### 2.5 Stage state

From `traverse` (labels from `engine.STATE_LABELS`):

| State | Rule |
|---|---|
| `entry` | v = e |
| `compromised` | v was reached by a propagated edge |
| `blocked` | not compromised, and at least one incoming evaluation is `blocked_by_controls` |
| `exposed` | not compromised, has incoming evaluations, none of them blocked |
| `unaffected` | no incoming evaluation |

### 2.6 Two passes: inherent and residual

`engine.simulate` runs the traversal twice:

* **inherent pass**: `traverse(..., L₀, coverage={}, ...)`, i.e. no controls at all;
* **residual pass**: `traverse(..., L_entry, coverage=P, ...)` with

```
L_entry = L₀ × (1 − P(e) / 100)
```

so preventive controls on the entry stage reduce the starting likelihood.

### 2.7 Stage risk

`risk.raw_risk` and `risk.residual_risk`:

```
raw(λ)          = λ × (σ / 5) × (ι / 5)                    # 0–100
inherent_risk(s) = raw(λ_inherent(s))
residual_risk(s) = raw(λ_residual(s)) × (1 − M(s) / 100)
```

Mitigating coverage is applied only to the residual value; the inherent value ignores every
control by construction.

### 2.8 Overall risk

The criticality-weighted average over **all** stages, including stages with zero risk
(`risk.weighted_overall`):

```
overall = Σ (risk(s) × w(s)) / Σ w(s)
```

The seeded weights are IDE 1, Version Control 2, CI/CD 2, Registry 2, Production 3
(Σw = 10). The weighted average uses the unrounded stage values (`exact_inherent`,
`exact_residual` in `engine.simulate`); only the result is rounded.

### 2.9 Rounding and classification

`risk.round_score` clamps to 0–100 and rounds half-up to one decimal place using `Decimal`
(so 0.05 → 0.1, not banker's rounding). Every stored and displayed score is rounded this way.
Classification (`risk.classify`) uses inclusive lower bounds:

| Band | Score |
|---|---|
| critical | ≥ 50 |
| high | ≥ 30 and < 50 |
| moderate | ≥ 15 and < 30 |
| low | < 15 |

Stage classifications use the rounded residual risk; the run's `classification` uses the
rounded overall residual risk. `peak_inherent_risk` and `peak_residual_risk` are the maxima of
the rounded stage values.

### 2.10 Counters

`compromised_count`: stages in `entry` or `compromised` in the residual pass.
`inherent_compromised_count`: the same in the inherent pass. `blocked_count`: residual
evaluations with outcome `blocked_by_controls`. `contained_count`: residual evaluations with
outcome `below_threshold`.

## 3. Worked example

**Scenario:** the seeded "Compromised Developer Account" (`threats/seed_data.py`): entry stage
IDE, L₀ = 70, σ = 4, ι = 4, τ = 50. Rules:

| Edge | p | Kind |
|---|---|---|
| IDE → Version Control | 85 | forward |
| IDE → CI/CD | 40 | bypass |
| Version Control → CI/CD | 80 | forward |
| CI/CD → Registry | 70 | forward |
| Registry → Production | 65 | forward |

**Enabled controls:** `mfa` (preventive, 60, protects IDE and Version Control),
`protected-branches` (preventive, 50, Version Control), `sca` (detective, 40, CI/CD and
Registry).

The severity-impact factor is (4/5) × (4/5) = 0.64 throughout.

### Step 1: coverage

| Stage | Preventive P | Mitigating M |
|---|---|---|
| IDE | MFA alone: 60 | 0 |
| Version Control | 100 × (1 − 0.4 × 0.5) = 80 | 0 |
| CI/CD | 0 | SCA: 40 |
| Registry | 0 | SCA: 40 |
| Production | 0 | 0 |

### Step 2: inherent pass (no controls)

| Order | Edge | effective | Outcome | Target likelihood |
|---|---|---|---|---|
| 1 | IDE → VCS | 85 | propagated | 70 × 0.85 = 59.5 |
| 2 | IDE → CI/CD | 40 | below threshold | (path through VCS is better) |
| 3 | VCS → CI/CD | 80 | propagated | 59.5 × 0.80 = 47.6 |
| 4 | CI/CD → Registry | 70 | propagated | 47.6 × 0.70 = 33.32 |
| 5 | Registry → Production | 65 | propagated | 33.32 × 0.65 = 21.658 |

Inherent stage risk = λ × 0.64: IDE 44.8, VCS 38.08, CI/CD 30.464, Registry 21.3248,
Production 13.8611. All five stages are compromised.

```
inherent overall = (44.8×1 + 38.08×2 + 30.464×2 + 21.3248×2 + 13.8611×3) / 10
                 = 266.121 / 10 = 26.6121  →  26.6 (moderate)
```

### Step 3: residual pass

L_entry = 70 × (1 − 60/100) = **28.0**.

| Order | Edge | effective | Outcome | transmitted |
|---|---|---|---|---|
| 1 | IDE → VCS | 85 × (1 − 0.80) = 17.0 | 17 < 50 but 85 ≥ 50 → **blocked by controls** | 28 × 0.17 = 4.76 |
| 2 | IDE → CI/CD | 40 × (1 − 0) = 40.0 | 40 < 50 and 40 < 50 → **below threshold** | 28 × 0.40 = 11.2 |

Nothing propagated, so the queue empties after IDE and the three VCS/CI/CD/Registry edges are
never evaluated.

| Stage | State | λ residual | raw = λ × 0.64 | × (1 − M/100) | residual risk |
|---|---|---|---|---|---|
| IDE | entry | 28.0 | 17.92 | × 1.0 | **17.9** (moderate) |
| Version Control | blocked | 4.76 | 3.0464 | × 1.0 | **3.0** (low) |
| CI/CD | exposed | 11.2 | 7.168 | × 0.6 | **4.3** (low) |
| Registry | unaffected | 0 | 0 | × 0.6 | **0.0** (low) |
| Production | unaffected | 0 | 0 | × 1.0 | **0.0** (low) |

```
residual overall = (17.92×1 + 3.0464×2 + 4.3008×2 + 0×2 + 0×3) / 10
                 = 32.6144 / 10 = 3.26144  →  3.3 (low)
```

Engine output (verbatim from `SimulationResult.explanation`):

> The attack starts at IDE / Developer Environment. With the enabled controls, 1 of 5 stages are
> modeled as compromised (IDE / Developer Environment).
> Overall residual risk is 3.3 (low), compared with an inherent risk of 26.6 (moderate) when no
> controls are applied.
> Controls reduce the number of compromised stages from 5 to 1.
> 1 propagation attempt(s) that would otherwise succeed were blocked by controls.
> 1 propagation attempt(s) fell below the 50% threshold without needing controls.
> The highest remaining stage risk is IDE / Developer Environment at 17.9.

Counters: `compromised_count` 1, `inherent_compromised_count` 5, `blocked_count` 1,
`contained_count` 1.

Two details that the example makes visible:

1. A **blocked** stage still carries risk (VCS 3.0) because its likelihood is the transmitted
   likelihood of the failed attempt. Blocking is not the same as zero risk.
2. SCA on the Registry has no effect here: the Registry was never reached, so there is no risk
   for it to mitigate. That is also why `recommend` skips controls whose stages all have zero
   residual risk.

## 4. Recommendations

`recommendations.recommend(inp, result, catalog, applicable_keys, limit=5)`:

1. Candidates are catalogue controls that are **not enabled** and protect **at least one stage
   whose residual risk is > 0**.
2. For each candidate the engine is re-run with the control added
   (`simulate_with_controls`).
3. `risk_reduction = round_score(current overall − trial overall)`; candidates with a
   reduction ≤ 0 are dropped.
4. Sorting key: largest reduction first, then controls the scenario lists as applicable
   (`ScenarioControl`), then lower effort (`low < medium < high`), then higher priority, then name.
5. The top five are kept. Each carries a generated `reason`, the protected stages, the edges it
   changes (for preventive controls) and the stages that would no longer be compromised.

For the worked example the stored recommendations are:

| Rank | Control | Reduction | Projected residual | Listed for the scenario? |
|---|---|---|---|---|
| 1 | `dependency-pinning` (preventive, 50, IDE + CI/CD) | 1.9 | 1.4 | no |
| 2 | `incident-response` (recovery, 25, all stages) | 0.9 | 2.4 | yes |
| 3 | `least-privilege` (preventive, 35, VCS…Production) | 0.6 | 2.7 | yes |
| 4 | `cicd-secrets` (preventive, 50, CI/CD) | 0.5 | 2.8 | no |
| 5 | `isolated-builds` (preventive, 45, CI/CD) | 0.4 | 2.9 | no |

Dependency pinning wins because it also protects the entry stage: P(IDE) becomes
100 × (1 − 0.4 × 0.5) = 80, so L_entry falls from 28 to 14.

## 5. Control contributions (leave-one-out)

`recommendations.control_contributions` re-runs the engine once per enabled control **without**
that control and reports `round_score(risk_without − risk_with)`:

| Control | Residual without it | Contribution |
|---|---|---|
| `mfa` | 10.4 | 7.1 |
| `protected-branches` | 3.9 | 0.6 |
| `sca` | 3.8 | 0.5 |

Contributions do not add up to the total reduction (26.6 − 3.3 = 23.3) because controls
interact: without MFA, protected branches alone still block IDE → VCS (85 × 0.5 = 42.5 < 50).
This is expected for a non-linear model and is why the report shows both views.

## 6. Determinism and reproducibility

* The engine has no randomness and no clock (Ruff rule `S311` is ignored project-wide with the
  comment "no cryptographic randomness used in the engine"; there is no `random` import in it).
* Outgoing edges are sorted by target position and controls by slug (`build_input`), so the
  order of rows in the database does not change the result (`test_edge_order_does_not_change_result`).
* Each run stores `input_snapshot` (snapshot version 2: scenario metadata, rules, applicable
  controls, control assumptions, and the exact engine input) and `result` (the full serialised
  `SimulationResult` plus recommendations and contributions). `input_from_snapshot` rebuilds the
  input; `test_snapshot_reproduces_the_stored_result` proves that re-running it gives the stored
  result.

## 7. Limitations (from `engine.LIMITATIONS`, plus observations)

Stated in the code and shown on every report's "Inputs and method" tab and on `/help/`:

1. Propagation uses a fixed threshold on modelled probabilities; it is a simplified model of
   conditional likelihood, not a calibrated prediction.
2. Control effectiveness values are illustrative teaching parameters.
3. Controls are assumed independent: combined coverage is 1 − ∏(1 − ε).
4. Stage likelihood follows the single most likely path; several paths are not summed.
5. No real-world telemetry; no real system is inspected.

Observed while documenting (not stated in the code):

6. The threshold makes outcomes discontinuous: moving an edge from 49 % to 50 % can compromise
   every downstream stage at once.
7. Severity and impact are per scenario, not per stage; only the weights differ between stages.
8. Overall risk is an average over all five stages, so an attack that stays in one heavily
   weighted stage can score lower than intuition suggests.
9. There is no uncertainty range (no Monte-Carlo mode); `docs/engineering-assessment.md` lists
   this as M8, future work.
