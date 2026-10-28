from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import analyst_required
from accounts.preferences import page_size, preferences_for
from audit.models import AuditAction
from audit.services import record_event
from remediation.services import tracked_controls
from threats.models import ScenarioStatus, SecurityControl, SupplyChainStage
from threats.services import visible_scenarios

from . import charts, services
from .engine import LIMITATIONS, STATE_LABELS, SimulationConfigError
from .exports import write_history_csv, write_run_csv
from .forms import SimulationForm
from .models import RunStatus
from .services import OUTCOME_LABELS
from .visual import build_pipeline


def _png_response(data):
    response = HttpResponse(data, content_type="image/png")
    response["Cache-Control"] = "private, max-age=300"
    return response


@login_required
def history(request):
    runs = services.accessible_runs(request.user)
    scope = request.GET.get("scope", "mine")
    if scope == "mine":
        runs = runs.filter(user=request.user)
    elif scope == "shared":
        runs = runs.filter(is_shared=True)
    status = request.GET.get("status", "")
    if status in RunStatus.values:
        runs = runs.filter(status=status)
    query = request.GET.get("q", "").strip()
    if query:
        runs = runs.filter(scenario_name__icontains=query)
    page = Paginator(runs, page_size(request)).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "reports/list.html",
        {
            "page_obj": page,
            "scope": scope,
            "status": status,
            "q": query,
            "querystring": params.urlencode(),
            "statuses": RunStatus.choices,
        },
    )


@login_required
def hub(request):
    """Simulations home: start a run from a scenario, or pick up recent work."""
    scenarios = visible_scenarios(request.user).filter(status=ScenarioStatus.ACTIVE).prefetch_related("rules")
    stages = list(SupplyChainStage.objects.all())
    by_stage = [(stage, [s for s in scenarios if s.initial_stage_id == stage.pk]) for stage in stages]
    recent = services.accessible_runs(request.user).filter(user=request.user)[:5]
    return render(
        request,
        "simulation/hub.html",
        {
            "by_stage": [(stage, items) for stage, items in by_stage if items],
            "recent": recent,
            "scenario_count": len(scenarios),
        },
    )


CONTROL_GROUPS = [
    ("preventive", "Preventive: lower the probability of reaching a protected stage"),
    ("detective", "Detective: reduce residual risk once a stage is reached"),
    ("recovery", "Recovery: reduce residual risk once a stage is reached"),
]

RESULT_SCOPES = {"all": "All visible", "mine": "Mine", "shared": "Shared with me"}


@login_required
def results(request):
    """Completed results as cards with each run's stage outcomes at a glance."""
    scope = request.GET.get("scope", "all")
    if scope not in RESULT_SCOPES:
        scope = "all"
    runs = services.accessible_runs(request.user).filter(status=RunStatus.COMPLETED)
    if scope == "mine":
        runs = runs.filter(user=request.user)
    elif scope == "shared":
        runs = runs.filter(is_shared=True).exclude(user=request.user)
    page = Paginator(runs.prefetch_related("stage_results"), page_size(request, 12)).get_page(request.GET.get("page"))
    return render(
        request,
        "simulation/results.html",
        {"page_obj": page, "scope": scope, "scopes": RESULT_SCOPES, "querystring": f"scope={scope}"},
    )


@analyst_required
def configure(request):
    scenarios = visible_scenarios(request.user)
    initial, selected_scenario = {}, None

    rerun_id = request.GET.get("rerun")
    if rerun_id:
        source = services.get_accessible_run(request.user, rerun_id)
        initial = {
            "scenario": source.scenario_slug,
            "likelihood": source.likelihood,
            "severity": source.severity,
            "impact": source.impact,
            "threshold": source.threshold,
            "controls": SecurityControl.objects.filter(slug__in=source.enabled_controls),
        }
    slug = request.POST.get("scenario") or request.GET.get("scenario") or initial.get("scenario")
    if slug:
        selected_scenario = scenarios.filter(slug=slug).first()
    if selected_scenario and not rerun_id:
        initial = {
            "scenario": selected_scenario.slug,
            "likelihood": selected_scenario.likelihood,
            "severity": selected_scenario.severity,
            "impact": selected_scenario.impact,
            "threshold": selected_scenario.propagation_threshold,
        }
    if rerun_id and selected_scenario is None:
        messages.warning(request, "The original scenario is no longer available, so this run cannot be repeated.")

    form = SimulationForm(request.POST or None, initial=initial, scenarios=scenarios)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            run = services.run_simulation(
                request.user,
                data["scenario"],
                likelihood=data["likelihood"],
                severity=data["severity"],
                impact=data["impact"],
                threshold=data["threshold"],
                controls=data["controls"],
                request=request,
            )
        except SimulationConfigError as exc:
            form.add_error(None, f"The scenario configuration is invalid: {exc}")
        else:
            if run.status == RunStatus.COMPLETED:
                if preferences_for(request.user).share_reports_by_default:
                    run.is_shared = True
                    run.save(update_fields=["is_shared"])
                    record_event(request.user, AuditAction.REPORT_SHARE, target=run, request=request, shared=True)
                messages.success(request, "Simulation completed.")
            else:
                messages.error(request, run.error_message)
            return redirect("simulation:detail", run_id=run.id)

    applicable = set()
    if selected_scenario:
        applicable = set(selected_scenario.controls.values_list("slug", flat=True))
    return render(
        request,
        "simulation/configure.html",
        {
            "form": form,
            "scenario": selected_scenario,
            "applicable": applicable,
            "controls": SecurityControl.objects.prefetch_related("stages").order_by("category", "name"),
            "pipeline": _scenario_preview(selected_scenario) if selected_scenario else None,
            "categories": CONTROL_GROUPS,
        },
    )


def _scenario_preview(scenario):
    stages = [
        {
            "key": s.key,
            "name": s.name,
            "position": s.position,
            "state": "entry" if s.pk == scenario.initial_stage_id else "rule",
        }
        for s in SupplyChainStage.objects.all()
    ]
    edges = [
        {"source": r.source.key, "target": r.target.key, "status": "rule", "label": f"{r.probability}%"}
        for r in scenario.rules.select_related("source", "target")
    ]
    return build_pipeline(stages, edges)


def _run_pipeline(run, stage_results, events):
    stages = [
        {"key": s.stage_key, "name": s.stage_name, "position": s.position, "state": s.state, "risk": s.residual_risk}
        for s in stage_results
    ]
    edges = [
        {"source": e.source_key, "target": e.target_key, "status": e.outcome, "label": f"{e.effective_probability:g}%"}
        for e in events
    ]
    evaluated = {(e.source_key, e.target_key) for e in events}
    for rule in run.input_snapshot.get("scenario", {}).get("rules", []):
        if (rule["source"], rule["target"]) not in evaluated:
            edges.append(
                {
                    "source": rule["source"],
                    "target": rule["target"],
                    "status": "not_evaluated",
                    "label": f"{rule['probability']:g}%",
                }
            )
    return build_pipeline(stages, edges)


RESULT_SECTIONS = {
    "summary": "Summary",
    "stages": "Stage analysis",
    "paths": "Propagation paths",
    "controls": "Controls and recommendations",
    "method": "Inputs and method",
}


def _result_context(request, run):
    stage_results = list(run.stage_results.all())
    events = list(run.events.all())
    # Exact counts for the outcome chart's text alternative.
    outcome_counts = {outcome: sum(1 for e in events if e.outcome == outcome) for outcome in OUTCOME_LABELS}
    snapshot_controls = run.input_snapshot.get("input", {}).get("controls", [])
    previous = (
        services.accessible_runs(request.user)
        .filter(
            user=run.user, scenario_slug=run.scenario_slug, status=RunStatus.COMPLETED, created_at__lt=run.created_at
        )
        .exclude(pk=run.pk)
        .first()
    )
    return {
        "run": run,
        "is_owner": run.user_id == request.user.pk,
        "stage_results": stage_results,
        "events": events,
        "outcome_counts": outcome_counts,
        "result": run.result,
        "pipeline": _run_pipeline(run, stage_results, events) if stage_results else None,
        "enabled_controls": snapshot_controls,
        "previous": previous,
        "limitations": run.result.get("limitations") or LIMITATIONS,
        "state_labels": STATE_LABELS,
        "scenario_changed": run.scenario is not None and run.scenario.version != run.scenario_version,
        "tracked": tracked_controls(request.user, run.scenario_slug),
        "affected_assets": _affected_assets(run, stage_results),
    }


def _affected_assets(run, stage_results):
    """Assets of the stages the run compromised (from the stage catalog)."""
    hit = [s for s in stage_results if s.state in ("entry", "compromised")]
    catalog = {s.key: s.assets for s in SupplyChainStage.objects.filter(key__in=[s.stage_key for s in hit])}
    return [
        {"stage": s, "assets": [a.strip() for a in catalog.get(s.stage_key, "").split(",") if a.strip()]} for s in hit
    ]


@login_required
def detail(request, run_id, section="summary"):
    if section not in RESULT_SECTIONS:
        raise Http404("Unknown section.")
    run = services.get_accessible_run(request.user, run_id)
    context = _result_context(request, run)
    context.update(section=section, sections=RESULT_SECTIONS)
    return render(request, "simulation/detail.html", context)


@login_required
def report_document(request, run_id):
    """The full assessment as one printable document (Reports area)."""
    run = services.get_accessible_run(request.user, run_id)
    return render(request, "reports/document.html", _result_context(request, run))


CHARTS = {"overall", "stages", "outcomes"}


@login_required
def chart(request, run_id, kind):
    if kind not in CHARTS:
        raise Http404("Unknown chart.")
    run = services.get_accessible_run(request.user, run_id)
    if run.status != RunStatus.COMPLETED:
        raise Http404("No chart for an incomplete run.")
    palette = charts.parse_palette(request.GET.get("palette"))
    if kind == "overall":
        data = charts.overall_risk_chart(run, palette)
    elif kind == "stages":
        data = charts.stage_risk_chart(list(run.stage_results.all()), palette)
    else:
        data = charts.outcome_chart(list(run.events.all()), palette)
    return _png_response(data)


def _compare_runs(request):
    run_a = services.get_accessible_run(request.user, request.GET.get("a", ""))
    run_b = services.get_accessible_run(request.user, request.GET.get("b", ""))
    if run_a.status != RunStatus.COMPLETED or run_b.status != RunStatus.COMPLETED:
        raise Http404("Both runs must be completed.")
    return run_a, run_b


@login_required
def compare(request):
    if not request.GET.get("a") or not request.GET.get("b"):
        runs = services.accessible_runs(request.user).filter(status=RunStatus.COMPLETED)[:50]
        return render(request, "simulation/compare_select.html", {"runs": runs})
    run_a, run_b = _compare_runs(request)
    return render(
        request,
        "simulation/compare.html",
        {"run_a": run_a, "run_b": run_b, "comparison": services.comparison(run_a, run_b), "state_labels": STATE_LABELS},
    )


@login_required
def compare_chart(request):
    run_a, run_b = _compare_runs(request)
    rows = services.comparison(run_a, run_b)["rows"]
    palette = charts.parse_palette(request.GET.get("palette"))
    return _png_response(charts.comparison_chart(run_a, run_b, rows, palette))


@login_required
@require_POST
def toggle_share(request, run_id):
    run = services.get_accessible_run(request.user, run_id)
    if run.user_id != request.user.pk:
        raise PermissionDenied("Only the owner can change sharing.")
    if run.status != RunStatus.COMPLETED:
        messages.error(request, "Only completed reports can be shared.")
        return redirect("simulation:detail", run_id=run.id)
    run.is_shared = not run.is_shared
    run.save(update_fields=["is_shared"])
    record_event(request.user, AuditAction.REPORT_SHARE, target=run, request=request, shared=run.is_shared)
    messages.success(request, "Report shared with all users." if run.is_shared else "Report is now private.")
    return redirect("simulation:detail", run_id=run.id)


def _csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_run(request, run_id):
    run = services.get_accessible_run(request.user, run_id)
    response = _csv_response(f"codeguard-run-{run.short_id}.csv")
    write_run_csv(response, run)
    record_event(request.user, AuditAction.REPORT_EXPORT, target=run, request=request, format="csv")
    return response


@login_required
def export_history(request):
    runs = services.accessible_runs(request.user).filter(user=request.user)
    response = _csv_response(f"codeguard-history-{timezone.now():%Y%m%d}.csv")
    write_history_csv(response, runs)
    record_event(request.user, AuditAction.REPORT_EXPORT, request=request, format="csv", scope="history")
    return response
