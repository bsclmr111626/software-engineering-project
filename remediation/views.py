from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import analyst_required
from accounts.preferences import page_size
from simulation.services import get_accessible_run

from . import services
from .forms import AssignForm, CommentForm, RemediationUpdateForm
from .models import ACTIVE_STATUSES, RemediationStatus

FILTERS = {
    "active": ("Open and in progress", ACTIVE_STATUSES),
    "overdue": ("Overdue", ACTIVE_STATUSES),
    **{status.value: (status.label, (status.value,)) for status in RemediationStatus},
    "all": ("All", None),
}

# Whose items: the plan opens on the person's own work.
SCOPES = {
    "mine": "Mine",
    "assigned": "Assigned to me",
    "team": "Everything I can see",
}

# Prioritisation orders for the plan.
SORTS = {
    "due": ("Due date", (F("due_date").asc(nulls_last=True), "-expected_reduction")),
    "impact": ("Largest modeled reduction", ("-expected_reduction", F("due_date").asc(nulls_last=True))),
    "recent": ("Recently added", ("-created_at",)),
}


def _scoped(user, scope):
    visible = services.items_for(user)
    if scope == "assigned":
        return visible.filter(assignee=user)
    if scope == "mine":
        return visible.filter(Q(owner=user) | Q(assignee=user))
    return visible


@login_required
def plan(request):
    key = request.GET.get("status", "active")
    if key not in FILTERS:
        key = "active"
    sort = request.GET.get("sort", "due")
    if sort not in SORTS:
        sort = "due"
    scope = request.GET.get("scope", "mine")
    if scope not in SCOPES:
        scope = "mine"
    today = timezone.localdate()
    everything = _scoped(request.user, scope)
    items = everything
    statuses = FILTERS[key][1]
    if statuses is not None:
        items = items.filter(status__in=statuses)
    if key == "overdue":
        items = items.filter(due_date__lt=today)
    items = items.order_by(*SORTS[sort][1])
    page = Paginator(items, page_size(request)).get_page(request.GET.get("page"))
    for item in page:
        item.verified_by = services.verification(item)
    counts = dict(everything.values_list("status").annotate(n=Count("id")).order_by())
    active = everything.filter(status__in=ACTIVE_STATUSES)
    summary = {
        "counts": {status.value: counts.get(status.value, 0) for status in RemediationStatus},
        "active": active.count(),
        "overdue": active.filter(due_date__lt=today).count(),
        "unscheduled": active.filter(due_date__isnull=True).count(),
        "unassigned": active.filter(assignee__isnull=True).count(),
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
            "scope": scope,
            "scopes": SCOPES,
            "summary": summary,
            "today": today,
            "querystring": f"scope={scope}&status={key}&sort={sort}",
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
    can_edit = services.can_edit(request.user, item)
    can_assign = services.can_assign(request.user, item)
    form = RemediationUpdateForm(request.POST or None, instance=item)
    if request.method == "POST":
        if not can_edit:
            messages.error(
                request, "Only the person who added this item, its assignee or an administrator can change it."
            )
            return redirect("remediation:detail", item.pk)
        if form.is_valid():
            services.update(
                request.user,
                item,
                status=form.cleaned_data["status"],
                note=form.cleaned_data["note"],
                due_date=form.cleaned_data["due_date"],
                evidence_url=form.cleaned_data["evidence_url"],
                request=request,
            )
            messages.success(request, "Remediation item updated.")
            return redirect("remediation:detail", item.pk)
    choices = services.assignable(item.workspace)
    return render(
        request,
        "remediation/detail.html",
        {
            "item": item,
            "form": form,
            "can_edit": can_edit,
            "can_assign": can_assign,
            "assign_form": AssignForm(
                initial={"assignee": item.assignee_id, "is_shared": item.is_shared}, choices=choices
            ),
            "comment_form": CommentForm(),
            "activity": item.activity.select_related("actor"),
            "verified_by": services.verification(item),
            "overdue": item.is_active and item.due_date and item.due_date < timezone.localdate(),
        },
    )


@login_required
@require_POST
def assign(request, pk):
    item = services.get_item(request.user, pk)
    if not services.can_assign(request.user, item):
        messages.error(request, "Only the person who added this item or an administrator can assign it.")
        return redirect("remediation:detail", item.pk)
    form = AssignForm(request.POST, choices=services.assignable(item.workspace))
    if not form.is_valid():
        messages.error(request, "Choose an analyst or administrator from this workspace.")
        return redirect("remediation:detail", item.pk)
    assignee = form.cleaned_data["assignee"]
    try:
        services.assign(
            request.user, item, assignee=assignee, is_shared=form.cleaned_data["is_shared"], request=request
        )
    except services.RemediationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Assignment and visibility saved.")
    return redirect("remediation:detail", item.pk)


@login_required
@require_POST
def comment(request, pk):
    item = services.get_item(request.user, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        services.comment(request.user, item, form.cleaned_data["comment"], request=request)
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Write a comment of up to 2,000 characters.")
    return redirect("remediation:detail", item.pk)
