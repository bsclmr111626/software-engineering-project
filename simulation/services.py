"""Bridge between the database and the pure simulation engine.

Run lifecycle (see docs/architecture.md, state diagram):

    PENDING --(engine + persistence succeed atomically)--> COMPLETED
    PENDING --(any error; partial rows rolled back)-------> FAILED
"""

import logging

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from threats.models import SecurityControl, SupplyChainStage

from . import engine
from . import propagation as prop
from .domain import Control, Edge, SimulationInput, Stage
from .models import PropagationEvent, RunStatus, SimulationRun, SimulationStageResult
from .recommendations import control_contributions, recommend
from .serialization import input_to_dict, result_to_dict

logger = logging.getLogger("codeguard.simulation")

# 2: adds "control_assumptions" (basis and limitations of each enabled control).
# Readers must tolerate its absence in version-1 snapshots.
SNAPSHOT_VERSION = 2

OUTCOME_LABELS = {
    prop.OUTCOME_PROPAGATED: "Propagated",
    prop.OUTCOME_BLOCKED: "Blocked by controls",
    prop.OUTCOME_BELOW_THRESHOLD: "Below threshold",
}


def control_to_domain(control):
    return Control(
        key=control.slug,
        name=control.name,
        effectiveness=float(control.effectiveness),
        stages=frozenset(s.key for s in control.stages.all()),
        category=control.category,
        effort=control.effort,
        priority=control.priority,
        addresses=control.addresses,
    )


def build_input(scenario, *, likelihood, severity, impact, threshold, controls):
    """Translate a scenario (plus user overrides) into an engine input."""
    stages = tuple(
        Stage(key=s.key, name=s.name, position=s.position, weight=s.weight)
        for s in SupplyChainStage.objects.order_by("position")
    )
    edges = tuple(
        Edge(source=r.source.key, target=r.target.key, probability=float(r.probability), rationale=r.rationale)
        for r in scenario.rules.select_related("source", "target")
    )
    return SimulationInput(
        stages=stages,
        entry_stage=scenario.initial_stage.key,
        likelihood=float(likelihood),
        severity=int(severity),
        impact=int(impact),
        edges=edges,
        controls=tuple(control_to_domain(c) for c in sorted(controls, key=lambda c: c.slug)),
        threshold=float(threshold),
    )


def input_from_snapshot(snapshot):
    """Rebuild the exact engine input stored with a historical run."""
    data = snapshot["input"]
    return SimulationInput(
        stages=tuple(Stage(**s) for s in data["stages"]),
        entry_stage=data["entry_stage"],
        likelihood=data["likelihood"],
        severity=data["severity"],
        impact=data["impact"],
        edges=tuple(Edge(**e) for e in data["edges"]),
        controls=tuple(Control(**{**c, "stages": frozenset(c["stages"])}) for c in data["controls"]),
        threshold=data["threshold"],
    )


def scenario_snapshot(scenario, inp, applicable, controls=()):
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "model_version": engine.MODEL_VERSION,
        "scenario": {
            "slug": scenario.slug,
            "name": scenario.name,
            "version": scenario.version,
            "description": scenario.description,
            "initial_stage": scenario.initial_stage.key,
            "visibility": scenario.visibility,
            "is_system": scenario.is_system,
            "assumptions": scenario.assumptions,
            "business_impact": scenario.business_impact,
            "rules": [
                {"source": e.source, "target": e.target, "probability": e.probability, "rationale": e.rationale}
                for e in inp.edges
            ],
        },
        "applicable_controls": sorted(applicable),
        "control_assumptions": {
            c.slug: {"effectiveness": c.effectiveness, "basis": c.effectiveness_basis, "limitations": c.limitations}
            for c in sorted(controls, key=lambda c: c.slug)
        },
        "input": input_to_dict(inp),
    }


def _event_explanation(evaluation, names):
    src, tgt = names[evaluation.source], names[evaluation.target]
    base = f"{src} → {tgt}: {evaluation.base_probability:g}%"
    if evaluation.target_coverage:
        base += f" reduced by {evaluation.target_coverage:g}% coverage to {evaluation.effective_probability:g}%"
    if evaluation.outcome == prop.OUTCOME_PROPAGATED:
        text = f"{base} ≥ {evaluation.threshold:g}% threshold, so the compromise propagates."
        if evaluation.target_already_compromised:
            text += " The target was already compromised, so it is not processed again."
    elif evaluation.outcome == prop.OUTCOME_BLOCKED:
        text = f"{base}, below the {evaluation.threshold:g}% threshold: blocked by controls."
    else:
        text = f"{base} is below the {evaluation.threshold:g}% threshold, so the model stops here."
    return text[:300]


def run_simulation(user, scenario, *, likelihood, severity, impact, threshold, controls, request=None):
    """Execute and persist a simulation. Raises SimulationConfigError for bad input."""
    controls = list(controls)
    inp = build_input(
        scenario, likelihood=likelihood, severity=severity, impact=impact, threshold=threshold, controls=controls
    )
    engine.validate_input(inp)  # invalid configurations never create a run
    applicable = set(scenario.controls.values_list("slug", flat=True))

    run = SimulationRun.objects.create(
        user=user,
        scenario=scenario,
        scenario_name=scenario.name,
        scenario_slug=scenario.slug,
        scenario_version=scenario.version,
        entry_stage_name=scenario.initial_stage.name,
        likelihood=likelihood,
        severity=severity,
        impact=impact,
        threshold=threshold,
        enabled_controls=sorted(c.slug for c in controls),
        input_snapshot=scenario_snapshot(scenario, inp, applicable, controls),
    )
    try:
        with transaction.atomic():
            _execute(run, inp, applicable)
    except Exception:
        logger.exception("Simulation run %s failed", run.pk)
        run.status = RunStatus.FAILED
        run.error_message = "The simulation could not be completed. The error has been logged."
        run.save(update_fields=["status", "error_message"])
        record_event(user, AuditAction.SIMULATION_FAILED, target=run, request=request, scenario=scenario.slug)
        return run

    record_event(
        user,
        AuditAction.SIMULATION_RUN,
        target=run,
        request=request,
        scenario=scenario.slug,
        residual_risk=run.residual_risk,
        controls=run.enabled_controls,
    )
    return run


def _execute(run, inp, applicable):
    result = engine.simulate(inp)
    catalog = [control_to_domain(c) for c in SecurityControl.objects.prefetch_related("stages").order_by("slug")]
    recommendations = recommend(inp, result, catalog, applicable)
    contributions = control_contributions(inp, result)
    names = {s.key: s.name for s in inp.stages}

    SimulationStageResult.objects.bulk_create(
        SimulationStageResult(
            run=run,
            stage_key=s.key,
            stage_name=s.name,
            position=s.position,
            state=s.state,
            inherent_state=s.inherent_state,
            inherent_likelihood=s.inherent_likelihood,
            residual_likelihood=s.residual_likelihood,
            preventive_coverage=s.preventive_coverage,
            mitigating_coverage=s.mitigating_coverage,
            inherent_risk=s.inherent_risk,
            residual_risk=s.residual_risk,
            classification=s.risk_classification,
            explanation=s.explanation,
        )
        for s in result.stages
    )
    PropagationEvent.objects.bulk_create(
        PropagationEvent(
            run=run,
            order=e.order,
            source_key=e.source,
            source_name=names[e.source],
            target_key=e.target,
            target_name=names[e.target],
            kind=e.kind,
            base_probability=e.base_probability,
            control_coverage=e.target_coverage,
            effective_probability=e.effective_probability,
            threshold=e.threshold,
            outcome=e.outcome,
            target_already_compromised=e.target_already_compromised,
            transmitted_likelihood=e.transmitted_likelihood,
            controls_applied=list(e.controls),
            explanation=_event_explanation(e, names),
        )
        for e in result.evaluations
    )
    run.result = result_to_dict(result, recommendations, contributions)
    run.inherent_risk = result.inherent_risk
    run.residual_risk = result.residual_risk
    run.classification = result.classification
    run.compromised_count = result.compromised_count
    run.blocked_count = result.blocked_count
    run.status = RunStatus.COMPLETED
    run.completed_at = timezone.now()
    run.save()


# --- Access control -------------------------------------------------------------


def accessible_runs(user):
    """Runs the user owns plus completed runs other users chose to share."""
    return SimulationRun.objects.filter(Q(user=user) | Q(is_shared=True, status=RunStatus.COMPLETED)).select_related(
        "user"
    )


def get_accessible_run(user, run_id):
    try:
        return accessible_runs(user).get(pk=run_id)
    except (SimulationRun.DoesNotExist, ValueError):
        raise Http404("Report not found.") from None


def comparison(run_a, run_b):
    """Stage-by-stage before/after comparison of two completed runs."""
    stages_a = {s.stage_key: s for s in run_a.stage_results.all()}
    stages_b = {s.stage_key: s for s in run_b.stage_results.all()}
    rows = []
    for key in sorted(set(stages_a) | set(stages_b), key=lambda k: (stages_a.get(k) or stages_b.get(k)).position):
        a, b = stages_a.get(key), stages_b.get(key)
        risk_a = a.residual_risk if a else 0.0
        risk_b = b.residual_risk if b else 0.0
        rows.append(
            {
                "name": (a or b).stage_name,
                "state_a": a.state if a else "",
                "state_b": b.state if b else "",
                "risk_a": risk_a,
                "risk_b": risk_b,
                "delta": round(risk_b - risk_a, 1),
                "state_changed": (a.state if a else "") != (b.state if b else ""),
            }
        )
    added = sorted(set(run_b.enabled_controls) - set(run_a.enabled_controls))
    removed = sorted(set(run_a.enabled_controls) - set(run_b.enabled_controls))
    return {
        "rows": rows,
        "controls_added": added,
        "controls_removed": removed,
        "delta": round(run_b.residual_risk - run_a.residual_risk, 1),
        "same_scenario": run_a.scenario_slug == run_b.scenario_slug,
    }
