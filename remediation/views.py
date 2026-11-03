from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import analyst_required, can_run_simulations
from accounts.preferences import page_size
from simulation.services import get_accessible_run

from . import services
from .forms import RemediationUpdateForm
from .models import ACTIVE_STATUSES, RemediationStatus

FILTERS = {
    "active": ("Open and in progress", ACTIVE_STATUSES),
    **{status.value: (status.label, (status.value,)) for status in RemediationStatus},
    "all": ("All", None),
}

# Prioritisation orders for the plan.
SORTS = {
    "due": ("Due date", (F("due_date").asc(nulls_last=True), "-expected_reduction")),
    "impact": ("Largest modeled reduction", ("-expected_reduction", F("due_date").asc(nulls_last=True))),
    "recent": ("Recently added", ("-created_at",)),
}


@login_required
def plan(request):
    key = request.GET.get("status", "active")
    if key not in FILTERS:
        key = "active"
    sort = request.GET.get("sort", "due")
    if sort not in SORTS:
        sort = "due"
    everything = services.items_for(request.user)
    items = everything
    statuses = FILTERS[key][1]
    if statuses is not None:
        items = items.filter(status__in=statuses)
    items = items.order_by(*SORTS[sort][1])
    page = Paginator(items, page_size(request)).get_page(request.GET.get("page"))
    for item in page:
        item.verified_by = services.verification(item)
    counts = dict(everything.values_list("status").annotate(n=Count("id")).order_by())
    active = everything.filter(status__in=ACTIVE_STATUSES)
    summary = {
        "counts": {status.value: counts.get(status.value, 0) for status in RemediationStatus},
        "active": active.count(),
        "overdue": active.filter(due_date__lt=timezone.localdate()).count(),
        "unscheduled": active.filter(due_date__isnull=True).count(),
        "expected": round(active.aggregate(total=Sum("expected_reduction"))["total"] or 0, 1),
    }
    return render(
        request,
        "remediation/plan.html",
        {
            "page_obj": page,
            "filters": FILTERS,
            "current": key,
            "sort": sort,
            "sorts": {k: v[0] for k, v in SORTS.items()},
            "summary": summary,
            "querystring": f"status={key}&sort={sort}",
        },
    )


@analyst_required
@require_POST
def track(request):
    run = get_accessible_run(request.user, request.POST.get("run", ""))
    try:
        item, created = services.track(request.user, run, request.POST.get("control", ""), request=request)
    except services.RemediationError as error:
        messages.error(request, str(error))
        return redirect("simulation:detail", run.pk)
    if created:
        messages.success(request, f"{item.control.name} was added to your remediation plan.")
    else:
        messages.info(request, f"{item.control.name} is already on your remediation plan.")
    return redirect("simulation:detail", run.pk)


@login_required
def detail(request, pk):
    item = services.get_item(request.user, pk)
    can_edit = can_run_simulations(request.user)
    form = RemediationUpdateForm(request.POST or None, instance=item)
    if request.method == "POST":
        if not can_edit:
            messages.error(request, "Your role does not permit changing remediation items.")
            return redirect("remediation:detail", item.pk)
        if form.is_valid():
            services.update(
                request.user,
                item,
                status=form.cleaned_data["status"],
                note=form.cleaned_data["note"],
                due_date=form.cleaned_data["due_date"],
                request=request,
            )
            messages.success(request, "Remediation item updated.")
            return redirect("remediation:detail", item.pk)
    return render(
        request,
        "remediation/detail.html",
        {"item": item, "form": form, "can_edit": can_edit, "verified_by": services.verification(item)},
    )
