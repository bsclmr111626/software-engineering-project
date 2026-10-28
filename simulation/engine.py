"""CodeGuard simulation engine.

``simulate()`` is the single entry point. It validates the input, runs the
propagation traversal twice and scores every stage:

* the *inherent* pass ignores all security controls;
* the *residual* pass applies the enabled controls.

The engine is deterministic: identical input always yields identical output.
It never touches the database; see ``simulation.services`` for persistence.
"""

from dataclasses import dataclass, field, replace

from . import propagation as prop
from .domain import MODE_MITIGATE, MODE_PREVENT
from .risk import (
    RiskInputError,
    classify,
    combined_effectiveness,
    raw_risk,
    residual_risk,
    round_score,
    validate_level,
    validate_percentage,
    weighted_overall,
)

MODEL_VERSION = "1.0"

LIMITATIONS = (
    "Propagation decisions use a fixed threshold on modeled probabilities; they are a "
    "simplified model of conditional likelihood, not a statistically calibrated prediction.",
    "Control effectiveness values are illustrative teaching parameters, not measured industry statistics.",
    "Controls are assumed to act independently, so combined coverage is 1 - product(1 - e).",
    "Stage likelihood follows the single most likely successful path; it does not sum "
    "the probability of several paths.",
    "The model uses no real-world telemetry and does not inspect any real system.",
)


class SimulationConfigError(ValueError):
    """Raised when a simulation input or graph configuration is invalid."""


@dataclass
class StageOutcome:
    key: str
    name: str
    position: int
    weight: int
    state: str
    inherent_state: str
    inherent_likelihood: float
    residual_likelihood: float
    preventive_coverage: float
    mitigating_coverage: float
    inherent_risk: float
    residual_risk: float
    risk_classification: str
    preventive_controls: tuple = ()
    mitigating_controls: tuple = ()
    explanation: str = ""


@dataclass
class SimulationResult:
    model_version: str
    entry_stage: str
    threshold: float
    stages: list
    evaluations: list
    inherent_risk: float
    residual_risk: float
    peak_inherent_risk: float
    peak_residual_risk: float
    inherent_classification: str
    classification: str
    compromised_count: int
    inherent_compromised_count: int
    blocked_count: int
    contained_count: int
    explanation: list = field(default_factory=list)
    limitations: tuple = LIMITATIONS

    def stage(self, key):
        return next(s for s in self.stages if s.key == key)


def validate_input(inp):
    """Reject invalid values and inconsistent graphs with clear messages."""
    if not inp.stages:
        raise SimulationConfigError("The supply chain must contain at least one stage.")
    keys = [s.key for s in inp.stages]
    if len(set(keys)) != len(keys):
        raise SimulationConfigError("Stage keys must be unique.")
    positions = [s.position for s in inp.stages]
    if len(set(positions)) != len(positions):
        raise SimulationConfigError("Stage positions must be unique.")
    for stage in inp.stages:
        if not isinstance(stage.weight, int) or stage.weight < 1:
            raise SimulationConfigError(f"Stage '{stage.key}' must have a weight of at least 1.")
    if inp.entry_stage not in keys:
        raise SimulationConfigError(f"Unknown entry stage '{inp.entry_stage}'.")

    try:
        validate_percentage(inp.likelihood, "Likelihood")
        validate_level(inp.severity, "Severity")
        validate_level(inp.impact, "Impact")
        validate_percentage(inp.threshold, "Propagation threshold")
        for edge in inp.edges:
            validate_percentage(edge.probability, f"Probability of {edge.source} -> {edge.target}")
        for control in inp.controls:
            validate_percentage(control.effectiveness, f"Effectiveness of '{control.key}'")
    except RiskInputError as exc:
        raise SimulationConfigError(str(exc)) from exc

    if inp.threshold <= 0:
        raise SimulationConfigError("Propagation threshold must be greater than 0.")

    seen = set()
    for edge in inp.edges:
        if edge.source not in keys or edge.target not in keys:
            raise SimulationConfigError(f"Propagation rule {edge.source} -> {edge.target} references an unknown stage.")
        if edge.source == edge.target:
            raise SimulationConfigError(f"Stage '{edge.source}' cannot propagate to itself.")
        if (edge.source, edge.target) in seen:
            raise SimulationConfigError(f"Duplicate propagation rule {edge.source} -> {edge.target}.")
        seen.add((edge.source, edge.target))

    control_keys = [c.key for c in inp.controls]
    if len(set(control_keys)) != len(control_keys):
        raise SimulationConfigError("Each control may only be enabled once.")
    for control in inp.controls:
        unknown = set(control.stages) - set(keys)
        if unknown:
            raise SimulationConfigError(
                f"Control '{control.key}' references unknown stage(s): {', '.join(sorted(unknown))}."
            )


def _coverage_by_stage(inp, mode):
    coverage, names = {}, {}
    for stage in inp.stages:
        applicable = [c for c in inp.controls if c.mode == mode and stage.key in c.stages]
        coverage[stage.key] = combined_effectiveness(c.effectiveness for c in applicable)
        names[stage.key] = tuple(c.key for c in applicable)
    return coverage, names


def simulate(inp):
    validate_input(inp)
    stages = {s.key: s for s in inp.stages}
    prevent_cov, prevent_names = _coverage_by_stage(inp, MODE_PREVENT)
    mitigate_cov, mitigate_names = _coverage_by_stage(inp, MODE_MITIGATE)

    inherent = prop.traverse(stages, inp.edges, inp.entry_stage, float(inp.likelihood), {}, {}, inp.threshold)
    entry_residual = float(inp.likelihood) * (1 - prevent_cov[inp.entry_stage] / 100)
    residual = prop.traverse(
        stages, inp.edges, inp.entry_stage, entry_residual, prevent_cov, prevent_names, inp.threshold
    )

    outcomes = []
    exact_inherent, exact_residual = {}, {}
    for stage in sorted(inp.stages, key=lambda s: s.position):
        inherent_value = raw_risk(inherent.likelihoods[stage.key], inp.severity, inp.impact)
        residual_value = residual_risk(
            raw_risk(residual.likelihoods[stage.key], inp.severity, inp.impact),
            mitigate_cov[stage.key],
        )
        exact_inherent[stage.key] = inherent_value
        exact_residual[stage.key] = residual_value
        outcome = StageOutcome(
            key=stage.key,
            name=stage.name,
            position=stage.position,
            weight=stage.weight,
            state=residual.states[stage.key],
            inherent_state=inherent.states[stage.key],
            inherent_likelihood=round_score(inherent.likelihoods[stage.key]),
            residual_likelihood=round_score(residual.likelihoods[stage.key]),
            preventive_coverage=round_score(prevent_cov[stage.key]),
            mitigating_coverage=round_score(mitigate_cov[stage.key]),
            inherent_risk=round_score(inherent_value),
            residual_risk=round_score(residual_value),
            risk_classification=classify(round_score(residual_value)),
            preventive_controls=prevent_names[stage.key],
            mitigating_controls=mitigate_names[stage.key],
        )
        outcome.explanation = _explain_stage(outcome, inp, stages, residual.evaluations)
        outcomes.append(outcome)

    weights = {s.key: s.weight for s in inp.stages}
    inherent_overall = round_score(weighted_overall((exact_inherent[k], weights[k]) for k in stages))
    residual_overall = round_score(weighted_overall((exact_residual[k], weights[k]) for k in stages))

    for evaluation in residual.evaluations:
        evaluation.target_coverage = round_score(evaluation.target_coverage)
        evaluation.effective_probability = round_score(evaluation.effective_probability)
        evaluation.transmitted_likelihood = round_score(evaluation.transmitted_likelihood)

    result = SimulationResult(
        model_version=MODEL_VERSION,
        entry_stage=inp.entry_stage,
        threshold=float(inp.threshold),
        stages=outcomes,
        evaluations=residual.evaluations,
        inherent_risk=inherent_overall,
        residual_risk=residual_overall,
        peak_inherent_risk=max(o.inherent_risk for o in outcomes),
        peak_residual_risk=max(o.residual_risk for o in outcomes),
        inherent_classification=classify(inherent_overall),
        classification=classify(residual_overall),
        compromised_count=sum(1 for s in residual.states.values() if s in prop.COMPROMISED_STATES),
        inherent_compromised_count=sum(1 for s in inherent.states.values() if s in prop.COMPROMISED_STATES),
        blocked_count=sum(1 for e in residual.evaluations if e.outcome == prop.OUTCOME_BLOCKED),
        contained_count=sum(1 for e in residual.evaluations if e.outcome == prop.OUTCOME_BELOW_THRESHOLD),
    )
    result.explanation = _explain_result(result, stages)
    return result


def simulate_with_controls(inp, controls):
    """Re-run ``inp`` with a different set of enabled controls."""
    return simulate(replace(inp, controls=tuple(controls)))


# --- Plain-language explanations -------------------------------------------------

STATE_LABELS = {
    prop.STATE_ENTRY: "Entry point",
    prop.STATE_COMPROMISED: "Compromised",
    prop.STATE_BLOCKED: "Blocked",
    prop.STATE_EXPOSED: "Exposed",
    prop.STATE_UNAFFECTED: "Unaffected",
}


def _explain_stage(outcome, inp, stages, evaluations):
    if outcome.state == prop.STATE_ENTRY:
        text = (
            f"The scenario assumes this stage is compromised with a base likelihood of {round_score(inp.likelihood)}%."
        )
        if outcome.preventive_coverage:
            text += (
                f" Preventive controls ({outcome.preventive_coverage}% combined coverage) "
                f"reduce it to {outcome.residual_likelihood}%."
            )
    else:
        incoming = [e for e in evaluations if e.target == outcome.key]
        if not incoming:
            text = "No modeled propagation path reached this stage."
        else:
            best = max(incoming, key=lambda e: e.effective_probability)
            source_name = stages[best.source].name
            if outcome.state == prop.STATE_COMPROMISED:
                text = (
                    f"Compromised via {source_name}: effective probability "
                    f"{round_score(best.effective_probability)}% met the "
                    f"{round_score(inp.threshold)}% threshold."
                )
            elif outcome.state == prop.STATE_BLOCKED:
                text = (
                    f"Propagation from {source_name} was blocked: controls reduced the edge "
                    f"probability from {round_score(best.base_probability)}% to "
                    f"{round_score(best.effective_probability)}%, below the "
                    f"{round_score(inp.threshold)}% threshold."
                )
            else:
                text = (
                    f"Exposed to {source_name}, but the effective probability "
                    f"({round_score(best.effective_probability)}%) is below the "
                    f"{round_score(inp.threshold)}% threshold, so the model stops here."
                )
    if outcome.mitigating_coverage and outcome.residual_risk:
        text += f" Detective/recovery controls reduce the stage risk by {outcome.mitigating_coverage}%."
    return text


def _explain_result(result, stages):
    entry_name = stages[result.entry_stage].name
    compromised = [s.name for s in result.stages if s.state in prop.COMPROMISED_STATES]
    lines = [
        f"The attack starts at {entry_name}. With the enabled controls, "
        f"{len(compromised)} of {len(result.stages)} stages are modeled as compromised "
        f"({', '.join(compromised)}).",
        f"Overall residual risk is {result.residual_risk} ({result.classification}), compared "
        f"with an inherent risk of {result.inherent_risk} ({result.inherent_classification}) "
        f"when no controls are applied.",
    ]
    if result.inherent_compromised_count != result.compromised_count:
        lines.append(
            f"Controls reduce the number of compromised stages from "
            f"{result.inherent_compromised_count} to {result.compromised_count}."
        )
    if result.blocked_count:
        lines.append(
            f"{result.blocked_count} propagation attempt(s) that would otherwise succeed were blocked by controls."
        )
    if result.contained_count:
        lines.append(
            f"{result.contained_count} propagation attempt(s) fell below the "
            f"{result.threshold:g}% threshold without needing controls."
        )
    peak = max(result.stages, key=lambda s: (s.residual_risk, -s.position))
    if peak.residual_risk > 0:
        lines.append(f"The highest remaining stage risk is {peak.name} at {peak.residual_risk}.")
    return lines
