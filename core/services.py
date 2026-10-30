"""Dashboard metrics, computed from the database on every request.

No metric is hardcoded: an empty database produces zeros and empty states.
"""

from collections import defaultdict

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from remediation.models import ACTIVE_STATUSES, RemediationItem
from simulation.models import RunStatus, SimulationStageResult
from simulation.services import accessible_runs
from threats.models import ScenarioStatus, SupplyChainStage
from threats.services import visible_scenarios

from . import svgcharts

BANDS = ("low", "moderate", "high", "critical")
EXPOSED_STATES = ("entry", "compromised", "blocked", "exposed")


def dashboard_metrics(user):
    runs = accessible_runs(user).filter(status=RunStatus.COMPLETED)
    summary = runs.aggregate(
        total=Count("id"),
        mine=Count("id", filter=Q(user=user)),
        average_residual=Avg("residual_risk"),
        average_inherent=Avg("inherent_risk"),
        high_risk=Count("id", filter=Q(classification__in=("high", "critical"))),
    )
    band_counts = dict(runs.values_list("classification").annotate(n=Count("id")).order_by())

    stage_rows = (
        SimulationStageResult.objects.filter(run__in=runs)
        .values("stage_key", "stage_name", "position")
        .annotate(
            exposed=Count("id", filter=Q(state__in=EXPOSED_STATES)),
            compromised=Count("id", filter=Q(state__in=("entry", "compromised"))),
            average_risk=Avg("residual_risk"),
        )
        .order_by("-compromised", "-exposed", "position")
    )

    stage_rows = list(stage_rows)
    by_stage = {row["stage_key"]: row for row in stage_rows}
    total = summary["total"] or 0
    stage_strip = [
        {
            "stage": stage,
            "compromised": by_stage.get(stage.key, {}).get("compromised", 0),
            "exposed": by_stage.get(stage.key, {}).get("exposed", 0),
            "average_risk": round(by_stage[stage.key]["average_risk"], 1) if stage.key in by_stage else None,
            "share": round(100 * by_stage.get(stage.key, {}).get("compromised", 0) / total) if total else 0,
        }
        for stage in SupplyChainStage.objects.all()
    ]
    band_rows = [
        {"label": band.title(), "value": band_counts.get(band, 0), "cls": f"bar-{band}", "band": band,
         "tip": f"{band.title()}: {band_counts.get(band, 0)} run(s)"}
        for band in reversed(BANDS)
    ]  # fmt: skip
    active_items = RemediationItem.objects.filter(owner=user, status__in=ACTIVE_STATUSES)
    return {
        "stage_strip": stage_strip,
        "band_chart": svgcharts.hbars(band_rows, max_value=max([r["value"] for r in band_rows] + [1]), width=520),
        "remediation_open": active_items.count(),
        "remediation_overdue": active_items.filter(due_date__lt=timezone.localdate()).count(),
        "next_items": list(
            active_items.select_related("control").order_by(F("due_date").asc(nulls_last=True), "-expected_reduction")[
                :3
            ]
        ),
        "scenario_count": visible_scenarios(user).filter(status=ScenarioStatus.ACTIVE).count(),
        "run_total": summary["total"],
        "run_mine": summary["mine"],
        "average_residual": round(summary["average_residual"], 1) if summary["average_residual"] is not None else None,
        "average_inherent": round(summary["average_inherent"], 1) if summary["average_inherent"] is not None else None,
        "high_risk": summary["high_risk"],
        "band_counts": [(band, band_counts.get(band, 0)) for band in BANDS],
        "band_dict": band_counts,
        "stage_rows": stage_rows,
        "recent_runs": list(accessible_runs(user).order_by("-created_at")[:6]),
        "recommended_controls": top_recommendations(runs.filter(user=user)[:10]),
    }


def top_recommendations(runs, limit=5):
    """Aggregate stored recommendations from the user's most recent runs."""
    totals = defaultdict(lambda: {"name": "", "count": 0, "total_reduction": 0.0, "effort": "", "control": ""})
    for run in runs:
        for rec in run.result.get("recommendations", []):
            entry = totals[rec["control"]]
            entry.update(name=rec["name"], effort=rec["effort"], control=rec["control"])
            entry["count"] += 1
            entry["total_reduction"] += rec["risk_reduction"]
    ranked = sorted(totals.values(), key=lambda e: (-e["count"], -e["total_reduction"], e["name"]))
    for entry in ranked:
        entry["average_reduction"] = round(entry["total_reduction"] / entry["count"], 1)
    return ranked[:limit]
