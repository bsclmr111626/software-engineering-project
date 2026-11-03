"""Remediation plan rules: creating items from recommendations, updating them,
and checking whether a later run confirms the change."""

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from simulation.models import RunStatus, SimulationRun
from threats.models import SecurityControl

from .models import ACTIVE_STATUSES, CLOSED_STATUSES, RemediationItem


class RemediationError(ValueError):
    """A request that cannot be turned into a remediation item."""


def items_for(user):
    return RemediationItem.objects.filter(owner=user).select_related("control", "source_run")


def get_item(user, pk):
    try:
        return items_for(user).get(pk=pk)
    except (RemediationItem.DoesNotExist, ValueError):
        raise Http404("Remediation item not found.") from None


def track(user, run, control_slug, request=None):
    """Add a recommendation from ``run`` to the user's plan. Returns (item, created)."""
    if run.status != RunStatus.COMPLETED:
        raise RemediationError("Only completed runs have recommendations.")
    recommendation = next(
        (r for r in run.result.get("recommendations", []) if r["control"] == control_slug),
        None,
    )
    if recommendation is None:
        raise RemediationError("That control is not one of this report's recommendations.")
    active = items_for(user).filter(
        scenario_slug=run.scenario_slug, control__slug=control_slug, status__in=ACTIVE_STATUSES
    )
    if active.exists():
        return active.get(), False
    control = SecurityControl.objects.get(slug=control_slug)
    try:
        with transaction.atomic():
            item = RemediationItem.objects.create(
                owner=user,
                control=control,
                scenario=run.scenario,
                scenario_slug=run.scenario_slug,
                scenario_name=run.scenario_name,
                source_run=run,
                baseline_risk=run.residual_risk,
                expected_reduction=max(0.0, recommendation["risk_reduction"]),
            )
    except IntegrityError:  # a concurrent request created it first
        return active.get(), False
    record_event(
        user,
        AuditAction.REMEDIATION_CREATE,
        target=item,
        request=request,
        control=control_slug,
        scenario=run.scenario_slug,
        run=str(run.pk),
    )
    return item, True


@transaction.atomic
def update(user, item, *, status, note, due_date, request=None):
    # Read the stored status: a bound ModelForm has already copied the new
    # values onto ``item`` during validation. The row lock serializes
    # concurrent updates so each audit event records the true transition.
    old_status = RemediationItem.objects.select_for_update().values_list("status", flat=True).get(pk=item.pk)
    item.status = status
    item.note = note
    item.due_date = due_date
    if status in CLOSED_STATUSES and old_status not in CLOSED_STATUSES:
        item.closed_at = timezone.now()
    elif status not in CLOSED_STATUSES:
        item.closed_at = None
    item.save()
    record_event(
        user,
        AuditAction.REMEDIATION_UPDATE,
        target=item,
        request=request,
        old_status=old_status,
        new_status=status,
    )
    return item


def verification(item):
    """The owner's latest completed run of the same scenario, made after the
    item was created, with the control enabled; or None."""
    candidates = SimulationRun.objects.filter(
        user_id=item.owner_id,
        scenario_slug=item.scenario_slug,
        status=RunStatus.COMPLETED,
        created_at__gt=item.created_at,
    ).order_by("-created_at")
    for run in candidates[:50]:
        if item.control.slug in run.enabled_controls:
            return run
    return None


def tracked_controls(user, scenario_slug):
    """{control slug: item} for the user's open and in-progress items on a scenario."""
    items = items_for(user).filter(scenario_slug=scenario_slug, status__in=ACTIVE_STATUSES)
    return {item.control.slug: item for item in items}
