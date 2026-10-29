from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import analyst_required, can_manage_scenarios, can_run_simulations
from accounts.preferences import page_size
from audit.models import AuditAction
from audit.services import record_event
from simulation.visual import build_pipeline

from . import services
from .forms import PropagationRuleFormSet, ScenarioFilterForm, ThreatScenarioForm, default_rules_for
from .models import ScenarioStatus, SecurityControl, SupplyChainStage


@login_required
def scenario_list(request):
    filter_form = ScenarioFilterForm(request.GET or None)
    scenarios = filter_form.filter(services.visible_scenarios(request.user))
    page = Paginator(scenarios.prefetch_related("rules"), page_size(request)).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    visible = services.visible_scenarios(request.user)
    return render(
        request,
        "threats/scenario_list.html",
        {
            "page_obj": page,
            "filter_form": filter_form,
            "querystring": query.urlencode(),
            "filtered": any(v for k, v in request.GET.items() if k != "page"),
            "totals": {
                "active": visible.filter(status=ScenarioStatus.ACTIVE).count(),
                "private": visible.filter(owner=request.user, visibility="private").count(),
                "archived": visible.filter(status=ScenarioStatus.ARCHIVED).count(),
            },
            "stages": SupplyChainStage.objects.all(),
        },
    )


def _scenario_pipeline(scenario):
    stages = [
        {
            "key": s.key,
            "name": s.name,
            "position": s.position,
            "state": "entry" if s == scenario.initial_stage else "rule",
        }
        for s in SupplyChainStage.objects.all()
    ]
    edges = [
        {"source": r.source.key, "target": r.target.key, "status": "rule", "label": f"{r.probability}%"}
        for r in scenario.rules.select_related("source", "target")
    ]
    return build_pipeline(stages, edges)


@login_required
def scenario_detail(request, slug):
    scenario = services.get_visible_scenario(request.user, slug)
    return render(
        request,
        "threats/scenario_detail.html",
        {
            "scenario": scenario,
            "rules": scenario.rules.select_related("source", "target"),
            "controls": scenario.controls.prefetch_related("stages"),
            "pipeline": _scenario_pipeline(scenario),
            "can_edit": services.can_edit(request.user, scenario),
            "can_delete": services.can_delete(request.user, scenario),
            "can_clone": can_manage_scenarios(request.user),
            "can_simulate": can_run_simulations(request.user) and scenario.is_active,
            "recent_runs": scenario.runs.filter(user=request.user)[:5],
        },
    )


def _edit_scenario(request, scenario=None):
    form = ThreatScenarioForm(request.POST or None, instance=scenario, user=request.user)
    initial = None
    if scenario is None and request.method != "POST":
        first_stage = SupplyChainStage.objects.order_by("position").first()
        initial = default_rules_for(first_stage) if first_stage else None
    formset = PropagationRuleFormSet(request.POST or None, instance=scenario, initial=initial, prefix="rules")
    if scenario is None and initial:
        formset.extra = len(initial)

    if request.method == "POST":
        form_valid = form.is_valid()
        if form_valid:
            formset.initial_stage = form.cleaned_data["initial_stage"]
        if form_valid and formset.is_valid():
            saved, created = services.save_scenario(form, formset, request.user)
            action = AuditAction.SCENARIO_CREATE if created else AuditAction.SCENARIO_UPDATE
            record_event(request.user, action, target=saved, request=request, version=saved.version)
            messages.success(request, f"Scenario “{saved.name}” {'created' if created else 'updated'}.")
            return redirect("threats:detail", slug=saved.slug)
        messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "threats/scenario_form.html",
        {"form": form, "formset": formset, "scenario": scenario},
    )


@analyst_required
def scenario_create(request):
    return _edit_scenario(request)


@analyst_required
def scenario_edit(request, slug):
    scenario = services.get_visible_scenario(request.user, slug)
    if not services.can_edit(request.user, scenario):
        raise PermissionDenied("You cannot edit this scenario.")
    return _edit_scenario(request, scenario)


@analyst_required
@require_POST
def scenario_archive(request, slug):
    scenario = services.get_visible_scenario(request.user, slug)
    if not services.can_edit(request.user, scenario):
        raise PermissionDenied("You cannot archive this scenario.")
    archiving = scenario.status == ScenarioStatus.ACTIVE
    scenario.status = ScenarioStatus.ARCHIVED if archiving else ScenarioStatus.ACTIVE
    scenario.save(update_fields=["status", "updated_at"])
    action = AuditAction.SCENARIO_ARCHIVE if archiving else AuditAction.SCENARIO_RESTORE
    record_event(request.user, action, target=scenario, request=request)
    messages.success(request, f"Scenario {'archived' if archiving else 'restored'}.")
    return redirect("threats:detail", slug=scenario.slug)


@analyst_required
def scenario_delete(request, slug):
    scenario = services.get_visible_scenario(request.user, slug)
    if not services.can_delete(request.user, scenario):
        raise PermissionDenied("This scenario cannot be deleted. System scenarios can only be archived.")
    if request.method == "POST":
        name = scenario.name
        with transaction.atomic():
            # Simulation runs keep their snapshot; their scenario link becomes NULL.
            record_event(request.user, AuditAction.SCENARIO_DELETE, target=scenario, request=request)
            scenario.delete()
        messages.success(request, f"Scenario “{name}” deleted. Historical reports were preserved.")
        return redirect("threats:list")
    return render(
        request, "threats/scenario_confirm_delete.html", {"scenario": scenario, "run_count": scenario.runs.count()}
    )


@analyst_required
@require_POST
def scenario_clone(request, slug):
    scenario = services.get_visible_scenario(request.user, slug)
    clone = services.clone_scenario(scenario, request.user)
    record_event(request.user, AuditAction.SCENARIO_CLONE, target=clone, request=request, source=scenario.slug)
    messages.success(request, f"Created a private copy of “{scenario.name}”. You can now edit it.")
    return redirect("threats:edit", slug=clone.slug)


@login_required
def control_list(request):
    controls = SecurityControl.objects.prefetch_related("stages")
    category = request.GET.get("category", "")
    stage = request.GET.get("stage", "")
    if category:
        controls = controls.filter(category=category)
    if stage:
        controls = controls.filter(stages__key=stage)
    all_controls = SecurityControl.objects.all()
    return render(
        request,
        "threats/control_list.html",
        {
            "category_counts": {
                c: all_controls.filter(category=c).count() for c in ("preventive", "detective", "recovery")
            },
            "control_total": all_controls.count(),
            "controls": controls.distinct(),
            "stages": SupplyChainStage.objects.all(),
            "selected_category": category,
            "selected_stage": stage,
        },
    )


@login_required
def control_detail(request, slug):
    control = get_object_or_404(SecurityControl.objects.prefetch_related("stages"), slug=slug)
    scenarios = services.visible_scenarios(request.user).filter(controls=control, status=ScenarioStatus.ACTIVE)
    return render(
        request,
        "threats/control_detail.html",
        {"control": control, "scenarios": scenarios, "example_effective": 80 * (100 - control.effectiveness) / 100},
    )
