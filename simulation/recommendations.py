"""Control recommendations and control-contribution analysis.

Every recommendation is traceable: the engine is re-run with the candidate
control added, and the recommendation reports the exact modeled change in
overall residual risk and in which stages remain compromised.
"""

from dataclasses import dataclass, field

from . import propagation as prop
from .domain import MODE_PREVENT
from .engine import simulate_with_controls
from .risk import round_score

EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Recommendation:
    control: str
    name: str
    category: str
    effort: str
    priority: str
    addresses: str
    scenario_applicable: bool
    protected_stages: list
    edges_addressed: list
    current_risk: float
    projected_risk: float
    risk_reduction: float
    stages_no_longer_compromised: list = field(default_factory=list)
    reason: str = ""


@dataclass
class ControlContribution:
    control: str
    name: str
    category: str
    protected_stages: list
    risk_without: float
    risk_with: float
    contribution: float


def _stage_names(inp):
    return {s.key: s.name for s in inp.stages}


def recommend(inp, result, catalog, applicable_keys=(), limit=5):
    """Rank disabled catalog controls by the modeled residual-risk reduction."""
    names = _stage_names(inp)
    enabled = {c.key for c in inp.controls}
    applicable_keys = set(applicable_keys)
    affected = {s.key for s in result.stages if s.residual_risk > 0}
    compromised_now = {s.key for s in result.stages if s.state in prop.COMPROMISED_STATES}

    recommendations = []
    for control in catalog:
        if control.key in enabled or not set(control.stages) & affected:
            continue
        trial = simulate_with_controls(inp, tuple(inp.controls) + (control,))
        reduction = round_score(result.residual_risk - trial.residual_risk)
        if reduction <= 0:
            continue
        compromised_after = {s.key for s in trial.stages if s.state in prop.COMPROMISED_STATES}
        protected = [names[k] for k in sorted(set(control.stages) & affected, key=_position(inp))]
        edges = []
        if control.mode == MODE_PREVENT:
            trial_edges = {(e.source, e.target): e for e in trial.evaluations}
            for evaluation in result.evaluations:
                if evaluation.target in control.stages:
                    after = trial_edges.get((evaluation.source, evaluation.target))
                    after_text = f"{after.effective_probability}%" if after else "not reached"
                    edges.append(
                        f"{names[evaluation.source]} → {names[evaluation.target]}: "
                        f"{evaluation.effective_probability}% → {after_text}"
                    )
        no_longer = [names[k] for k in sorted(compromised_now - compromised_after, key=_position(inp))]
        reason = (
            f"Protects {', '.join(protected)}. Enabling it lowers modeled residual risk from "
            f"{result.residual_risk} to {trial.residual_risk} ({reduction} points)."
        )
        if no_longer:
            reason += f" It stops propagation into {', '.join(no_longer)}."
        recommendations.append(
            Recommendation(
                control=control.key,
                name=control.name,
                category=control.category,
                effort=control.effort,
                priority=control.priority,
                addresses=control.addresses,
                scenario_applicable=control.key in applicable_keys,
                protected_stages=protected,
                edges_addressed=edges,
                current_risk=result.residual_risk,
                projected_risk=trial.residual_risk,
                risk_reduction=reduction,
                stages_no_longer_compromised=no_longer,
                reason=reason,
            )
        )

    recommendations.sort(
        key=lambda r: (
            -r.risk_reduction,
            not r.scenario_applicable,
            EFFORT_RANK.get(r.effort, 1),
            PRIORITY_RANK.get(r.priority, 1),
            r.name,
        )
    )
    return recommendations[:limit] if limit else recommendations


def control_contributions(inp, result):
    """How much residual risk each enabled control removes (leave-one-out)."""
    names = _stage_names(inp)
    contributions = []
    for control in inp.controls:
        others = tuple(c for c in inp.controls if c.key != control.key)
        without = simulate_with_controls(inp, others)
        contributions.append(
            ControlContribution(
                control=control.key,
                name=control.name,
                category=control.category,
                protected_stages=[names[k] for k in sorted(control.stages, key=_position(inp))],
                risk_without=without.residual_risk,
                risk_with=result.residual_risk,
                contribution=round_score(without.residual_risk - result.residual_risk),
            )
        )
    contributions.sort(key=lambda c: (-c.contribution, c.name))
    return contributions


def _position(inp):
    positions = {s.key: s.position for s in inp.stages}
    return lambda key: positions[key]
