"""Read-only aggregations for the Supply chain and Risk analysis areas.

Like the overview metrics (services.py), everything is computed from the
database on each request and scoped to what the user may see: shared or own
scenarios, and their own runs plus reports others have shared.
"""

from collections import defaultdict

from django.db.models import Avg, Count, Q

from simulation.models import RunStatus, SimulationStageResult
from simulation.services import accessible_runs
from simulation.visual import build_pipeline
from threats.models import PropagationRule, ScenarioStatus, SecurityControl, SupplyChainStage
from threats.services import visible_scenarios

from . import svgcharts

EXPOSED_STATES = ("entry", "compromised", "blocked", "exposed")
BANDS_HIGH_FIRST = ("critical", "high", "moderate", "low")


def split_assets(text):
    return [a.strip() for a in text.replace(";", ",").split(",") if a.strip()]


def _rounded(value):
    return round(value, 1) if value is not None else None


def _edge_kind(source_position, target_position):
    if target_position == source_position + 1:
        return "forward"
    return "bypass" if target_position > source_position else "reverse"


def _stage_exposure(runs):
    rows = (
        SimulationStageResult.objects.filter(run__in=runs)
        .values("stage_key")
        .annotate(
            reached=Count("id", filter=Q(state__in=EXPOSED_STATES)),
            compromised=Count("id", filter=Q(state__in=("entry", "compromised"))),
            blocked=Count("id", filter=Q(state="blocked")),
            average_inherent=Avg("inherent_risk"),
            average_residual=Avg("residual_risk"),
            runs=Count("id"),
        )
    )
    return {row["stage_key"]: row for row in rows}


def supply_chain_map(user):
    """Stages with their assets, controls, entry scenarios, configured
    propagation paths across visible scenarios, and run exposure."""
    scenarios = visible_scenarios(user).filter(status=ScenarioStatus.ACTIVE)
    stages = list(SupplyChainStage.objects.prefetch_related("controls"))
    entry_counts = dict(scenarios.values_list("initial_stage__key").annotate(n=Count("id")).order_by())
    runs = accessible_runs(user).filter(status=RunStatus.COMPLETED)
    exposure = _stage_exposure(runs)

    edges = (
        PropagationRule.objects.filter(scenario__in=scenarios)
        .values("source__key", "source__name", "source__position", "target__key", "target__name", "target__position")
        .annotate(scenarios=Count("scenario", distinct=True), average=Avg("probability"))
        .order_by("source__position", "target__position")
    )
    edge_list = [
        {
            "source": e["source__key"],
            "target": e["target__key"],
            "source_name": e["source__name"],
            "target_name": e["target__name"],
            "kind": _edge_kind(e["source__position"], e["target__position"]),
            "scenarios": e["scenarios"],
            "average": round(e["average"], 1),
        }
        for e in edges
    ]

    out = []
    for stage in stages:
        stats = exposure.get(stage.key, {})
        out.append(
            {
                "stage": stage,
                "assets": split_assets(stage.assets),
                "controls": list(stage.controls.all()),
                "entry_scenarios": entry_counts.get(stage.key, 0),
                "inbound": [e for e in edge_list if e["target"] == stage.key],
                "outbound": [e for e in edge_list if e["source"] == stage.key],
                "reached": stats.get("reached", 0),
                "compromised": stats.get("compromised", 0),
                "average_residual": _rounded(stats.get("average_residual")),
            }
        )
    pipeline = build_pipeline(
        [{"key": s.key, "name": s.name, "position": s.position, "state": "rule"} for s in stages],
        [
            {"source": e["source"], "target": e["target"], "status": "rule", "label": f"{e['average']:g}%"}
            for e in edge_list
        ],
    )
    return {
        "stages": out,
        "pipeline": pipeline,
        "edges": edge_list,
        "scenario_count": scenarios.count(),
        "run_count": runs.count(),
        "control_count": SecurityControl.objects.count(),
        "asset_count": sum(len(s["assets"]) for s in out),
    }


def stage_profile(user, stage):
    scenarios = visible_scenarios(user).filter(status=ScenarioStatus.ACTIVE)
    runs = accessible_runs(user).filter(status=RunStatus.COMPLETED)
    stats = _stage_exposure(runs).get(stage.key, {})
    results = (
        SimulationStageResult.objects.filter(run__in=runs, stage_key=stage.key)
        .select_related("run")
        .order_by("-run__created_at")[:8]
    )
    rules = list(PropagationRule.objects.filter(scenario__in=scenarios).select_related("scenario", "source", "target"))
    return {
        "assets": split_assets(stage.assets),
        "controls": stage.controls.order_by("category", "name"),
        "entry_scenarios": scenarios.filter(initial_stage=stage),
        "inbound": [r for r in rules if r.target_id == stage.pk],
        "outbound": [r for r in rules if r.source_id == stage.pk],
        "stats": {
            "runs": stats.get("runs", 0),
            "reached": stats.get("reached", 0),
            "compromised": stats.get("compromised", 0),
            "blocked": stats.get("blocked", 0),
            "average_inherent": _rounded(stats.get("average_inherent")),
            "average_residual": _rounded(stats.get("average_residual")),
        },
        "recent_results": results,
    }


def _control_effects(runs):
    """Average modeled contribution of each control across the runs that
    enabled it (from each run's stored "remove one control" re-runs)."""
    totals = defaultdict(lambda: {"name": "", "slug": "", "runs": 0, "total": 0.0, "category": ""})
    for run in runs.select_related(None).only("id", "result")[:200]:
        for c in run.result.get("control_contributions", []):
            entry = totals[c["control"]]
            entry.update(name=c["name"], slug=c["control"], category=c.get("category", ""))
            entry["runs"] += 1
            entry["total"] += c["contribution"]
    rows = [{**e, "average": round(e["total"] / e["runs"], 1)} for e in totals.values()]
    return sorted(rows, key=lambda e: (-e["average"], e["name"]))[:10]


def risk_analysis(user, scope="all", scenario_slug=""):
    runs = accessible_runs(user).filter(status=RunStatus.COMPLETED)
    if scope == "mine":
        runs = runs.filter(user=user)
    if scenario_slug:
        runs = runs.filter(scenario_slug=scenario_slug)
    ordered = list(runs.order_by("-created_at")[:24])[::-1]  # the 24 latest, oldest first

    summary = runs.aggregate(total=Count("id"), inherent=Avg("inherent_risk"), residual=Avg("residual_risk"))
    inherent = _rounded(summary["inherent"])
    residual = _rounded(summary["residual"])

    trend = svgcharts.line_chart(
        [
            {"name": "Inherent risk", "cls": "series-inherent", "values": [r.inherent_risk for r in ordered]},
            {"name": "Residual risk", "cls": "series-residual", "values": [r.residual_risk for r in ordered]},
        ],
        [r.created_at.strftime("%d %b") for r in ordered],
    )
    for column, run in zip(trend["columns"], ordered, strict=True):
        column["run"] = run

    exposure = _stage_exposure(runs)
    stage_rows = []
    for stage in SupplyChainStage.objects.all():
        stats = exposure.get(stage.key, {})
        stage_rows.append(
            {
                "label": stage.name,
                "key": stage.key,
                "a": _rounded(stats.get("average_inherent")),
                "b": _rounded(stats.get("average_residual")),
                "reached": stats.get("reached", 0),
                "compromised": stats.get("compromised", 0),
                "runs": stats.get("runs", 0),
            }
        )

    control_rows = _control_effects(runs)
    top = max((r["average"] for r in control_rows), default=0)
    control_chart = svgcharts.hbars(
        [
            {
                "label": r["name"],
                "value": r["average"],
                "cls": "bar-control",
                "tip": f"{r['name']}: −{r['average']} points on average across {r['runs']} run(s)",
            }
            for r in control_rows
        ],
        max_value=max(top, 1),
        width=330,
        row_height=30,
    )

    band_counts = dict(runs.values_list("classification").annotate(n=Count("id")).order_by())
    scenarios = (
        accessible_runs(user)
        .filter(status=RunStatus.COMPLETED)
        .values_list("scenario_slug", "scenario_name")
        .distinct()
        .order_by("scenario_name")
    )
    return {
        "total": summary["total"],
        "inherent": inherent,
        "residual": residual,
        "reduction": round(inherent - residual, 1) if inherent is not None and residual is not None else None,
        "trend": trend,
        "trend_runs": ordered,
        "stage_rows": stage_rows,
        "stage_chart": svgcharts.paired_columns(stage_rows, width=520, height=260, column=16),
        "control_rows": control_rows,
        "control_chart": control_chart,
        "bands": [(band, band_counts.get(band, 0)) for band in BANDS_HIGH_FIRST],
        "scenario_options": list(dict(scenarios).items()),
    }
