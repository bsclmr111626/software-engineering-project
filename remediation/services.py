"""Remediation plan rules: creating items from recommendations, updating them,
and checking whether a later run confirms the change."""

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from simulation.models import RunStatus, SimulationRun
from threats.models import SecurityControl
from code_scans.models import CodeFinding
from .models import CodeFindingRemediation

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


# CodeQL finding remediation

CODE_REMEDIATION_GUIDANCE = {
    "py/command-line-injection": (
        "Avoid passing user-controlled input to os.system(), os.popen(), "
        "or subprocess functions with shell=True. Prefer subprocess.run() "
        "with a list of arguments and shell=False. Validate arguments "
        "against an allowlist, avoid constructing shell command strings, "
        "and apply an appropriate timeout."
    ),
    "js/command-line-injection": (
        "Avoid passing user-controlled input to child_process.exec(). "
        "Prefer execFile() or spawn() with an argument array and shell "
        "disabled. Validate commands and arguments against an allowlist "
        "and avoid constructing shell command strings."
    ),
    "py/sql-injection": (
        "Use parameterized SQL queries instead of building SQL statements "
        "by concatenating user input. Use your database library's parameter "
        "binding facilities and avoid interpolating untrusted values into "
        "SQL strings."
    ),
    "js/sql-injection": (
        "Use parameterized queries or prepared statements instead of "
        "concatenating user-controlled input into SQL statements. Use the "
        "parameter-binding facilities provided by your database library."
    ),
    "py/path-injection": (
        "Validate user-supplied file paths. Resolve the requested path "
        "and verify that it remains inside an approved base directory "
        "before reading or writing files. Do not rely on string-prefix "
        "checks alone."
    ),
    "js/path-injection": (
        "Validate user-supplied file paths and resolve them against an "
        "approved base directory. Verify that the resolved path remains "
        "inside that directory before accessing the filesystem."
    ),
}


def recommendation_for(finding):
    """Return remediation guidance for a CodeQL finding."""
    guidance = CODE_REMEDIATION_GUIDANCE.get(finding.rule_id)

    if guidance:
        return guidance

    return (
        "Review this finding and follow the security guidance for the "
        "identified CodeQL rule. Examine the affected source file and "
        "reported line, identify the underlying unsafe operation, and "
        "apply a secure alternative. Consult the CodeQL rule documentation "
        "for additional details."
    )


def code_items_for(user):
    """Return code remediation items belonging to the user's scans."""
    return (
        CodeFindingRemediation.objects
        .filter(finding__scan__owner=user)
        .select_related("finding", "finding__scan")
    )


def get_code_item(user, pk):
    """Retrieve a code remediation item while enforcing ownership."""
    try:
        return code_items_for(user).get(pk=pk)
    except (CodeFindingRemediation.DoesNotExist, ValueError):
        raise Http404("Code remediation item not found.") from None


def track_code_finding(user, finding, request=None):
    """Add a CodeQL finding to the remediation plan.

    Returns (item, created).
    """
    if finding.scan.owner_id != user.pk:
        raise Http404("Code finding not found.")

    existing = code_items_for(user).filter(finding=finding).first()

    if existing:
        return existing, False

    try:
        with transaction.atomic():
            item = CodeFindingRemediation.objects.create(
                finding=finding,
                recommendation=recommendation_for(finding),
            )
    except IntegrityError:
        # Another request may have created the item simultaneously.
        existing = code_items_for(user).get(finding=finding)
        return existing, False

    record_event(
        user,
        AuditAction.REMEDIATION_CREATE,
        target=item,
        request=request,
        finding=str(finding.pk),
        rule_id=finding.rule_id,
        scan=str(finding.scan_id),
    )

    return item, True


@transaction.atomic
def update_code_item(user, item, *, status, note, due_date, request=None):
    """Update a code finding's remediation status and notes."""

    old_status = (
        CodeFindingRemediation.objects
        .select_for_update()
        .values_list("status", flat=True)
        .get(
            pk=item.pk,
            finding__scan__owner=user,
        )
    )

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
        rule_id=item.finding.rule_id,
    )

    return item
