import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_GET, require_POST

from accounts.preferences import START_PAGE_URLS, preferences_for
from simulation import charts
from simulation.engine import LIMITATIONS
from simulation.models import RunStatus
from simulation.risk import RISK_BANDS
from simulation.services import accessible_runs
from threats.models import SecurityControl, SupplyChainStage, ThreatScenario

from . import analytics
from .notifications import notifications_for
from .services import dashboard_metrics

logger = logging.getLogger("codeguard")


@require_GET
@never_cache
def healthz(request):
    """Liveness and readiness probe for load balancers and monitoring.

    Public by design, so it reveals nothing beyond up/down: no version,
    hostnames or error details (failures are logged server-side instead).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check: database unavailable")
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})


def landing(request):
    """The public product page. Its figures are live counts, never claims."""
    return render(
        request,
        "core/landing.html",
        {
            "stages": SupplyChainStage.objects.all(),
            "scenario_total": ThreatScenario.objects.filter(is_system=True).count(),
            "control_total": SecurityControl.objects.count(),
            "bands": RISK_BANDS,
        },
    )


@login_required
def start(request):
    """Where sign-in lands: the start page chosen in Settings > Display."""
    return redirect(START_PAGE_URLS.get(preferences_for(request.user).start_page, "core:dashboard"))


@login_required
def dashboard(request):
    return render(request, "dashboard/dashboard.html", {"metrics": dashboard_metrics(request.user)})


@login_required
def dashboard_redirect(request):
    return redirect("core:dashboard", permanent=True)


@login_required
def dashboard_chart(request):
    metrics = dashboard_metrics(request.user)
    palette = charts.parse_palette(request.GET.get("palette"))
    response = HttpResponse(charts.distribution_chart(metrics["band_dict"], palette), content_type="image/png")
    response["Cache-Control"] = "private, max-age=60"
    return response


@login_required
def supply_chain(request):
    return render(request, "supply_chain/overview.html", {"map": analytics.supply_chain_map(request.user)})


@login_required
def stage_detail(request, key):
    stage = get_object_or_404(SupplyChainStage, key=key)
    stages = list(SupplyChainStage.objects.all())
    index = stages.index(stage)
    return render(
        request,
        "supply_chain/stage.html",
        {
            "stage": stage,
            "stages": stages,
            "previous_stage": stages[index - 1] if index > 0 else None,
            "next_stage": stages[index + 1] if index + 1 < len(stages) else None,
            "profile": analytics.stage_profile(request.user, stage),
        },
    )


RISK_SCOPES = {"all": "All visible runs", "mine": "My runs"}


@login_required
def risk(request):
    scope = request.GET.get("scope", "all")
    if scope not in RISK_SCOPES:
        scope = "all"
    scenario = request.GET.get("scenario", "")
    analysis = analytics.risk_analysis(request.user, scope=scope, scenario_slug=scenario)
    if scenario and scenario not in dict(analysis["scenario_options"]):
        scenario = ""
    compare_runs = accessible_runs(request.user).filter(status=RunStatus.COMPLETED)[:50]
    return render(
        request,
        "risk/analysis.html",
        {
            "analysis": analysis,
            "scope": scope,
            "scopes": RISK_SCOPES,
            "scenario": scenario,
            "compare_runs": compare_runs,
        },
    )


@login_required
def notifications(request):
    return render(request, "core/notifications.html", {"notifications": notifications_for(request.user)})


@login_required
@require_POST
def notifications_read(request):
    preferences = preferences_for(request.user)
    preferences.notifications_seen_at = timezone.now()
    preferences.save(update_fields=["notifications_seen_at", "updated_at"])
    messages.success(request, "All notifications are marked as read.")
    return redirect("core:notifications")


def methodology(request):
    return render(
        request,
        "core/help.html",
        {
            "layout": "layouts/app.html" if request.user.is_authenticated else "layouts/public.html",
            "stages": SupplyChainStage.objects.prefetch_related("controls"),
            "controls": SecurityControl.objects.order_by("category", "name"),
            "limitations": LIMITATIONS,
            "bands": RISK_BANDS,
        },
    )


# --- Error handlers: friendly pages, never stack traces ------------------------


def _error(request, template, status):
    return HttpResponse(loader.render_to_string(template, {}, request), status=status)


@requires_csrf_token
def bad_request(request, exception=None):
    return _error(request, "errors/400.html", 400)


@requires_csrf_token
def permission_denied(request, exception=None):
    return _error(request, "errors/403.html", 403)


@requires_csrf_token
def page_not_found(request, exception=None):
    return _error(request, "errors/404.html", 404)


@requires_csrf_token
def server_error(request):
    logger.error("Unhandled server error on %s", request.path)
    return _error(request, "errors/500.html", 500)


def csrf_failure(request, reason=""):
    return _error(request, "errors/403_csrf.html", 403)
