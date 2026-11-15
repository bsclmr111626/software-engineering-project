from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import is_admin
from accounts.preferences import page_size
from accounts.workspaces import workspace_of

from .models import AuditAction, AuditEvent

# A visual category for each action in the activity timeline.
CATEGORY = {
    **dict.fromkeys(
        [
            "login",
            "logout",
            "login_failed",
            "login_throttled",
            "register",
            "password_change",
            "email_change",
            "sessions_revoked",
        ],
        "access",
    ),
    **dict.fromkeys(
        [
            "scenario_create",
            "scenario_update",
            "scenario_archive",
            "scenario_restore",
            "scenario_delete",
            "scenario_clone",
        ],
        "library",
    ),
    **dict.fromkeys(["simulation_run", "simulation_failed", "report_share", "report_export"], "simulation"),
    **dict.fromkeys(
        ["remediation_create", "remediation_update", "remediation_assign", "remediation_comment"], "remediation"
    ),
    **dict.fromkeys(["role_change", "audit_purge", "profile_update", "preferences_update", "data_export"], "admin"),
}


@login_required
def audit_log(request):
    """Administrators see every event of their workspace; other users see only
    their own. Events of other workspaces, and events that belong to no
    workspace, are never shown here (platform staff use the Django admin)."""
    if is_admin(request.user):
        events = AuditEvent.objects.filter(workspace=workspace_of(request.user))
    else:
        events = AuditEvent.objects.filter(actor=request.user)

    action = request.GET.get("action", "")
    if action in AuditAction.values:
        events = events.filter(action=action)
    user_query = request.GET.get("user", "").strip()
    if user_query and is_admin(request.user):
        events = events.filter(actor_username__icontains=user_query)

    view = request.GET.get("view", "timeline")
    if view not in ("timeline", "table"):
        view = "timeline"
    page = Paginator(events, page_size(request)).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    days = []
    for event in page:
        day = timezone.localtime(event.created_at).date()
        if not days or days[-1][0] != day:
            days.append((day, []))
        days[-1][1].append(event)
    return render(
        request,
        "audit/log.html",
        {
            "page_obj": page,
            "actions": AuditAction.choices,
            "selected_action": action,
            "user_query": user_query,
            "show_all": is_admin(request.user),
            "querystring": params.urlencode(),
            "view": view,
            "days": days,
            "category_of": CATEGORY,
        },
    )
