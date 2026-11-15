"""Remediation plan rules: creating items from recommendations, who may see,
change and assign them, their history, and checking whether a later run
confirms the change.

Visibility (``items_for``): the owner, the assignee and, for shared items,
every member of the item's workspace. Changing status, due date, notes and
evidence: the owner, the assignee and workspace administrators, provided
their role can act (analyst or administrator). Assigning and sharing: the
owner and workspace administrators. Comments: anyone who can see the item.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from accounts import emails
from accounts.models import Role
from accounts.permissions import can_run_simulations, is_admin
from accounts.preferences import preferences_for
from accounts.workspaces import members, workspace_of
from audit.models import AuditAction
from audit.services import record_event
from core.email import delivers_email
from simulation.models import RunStatus, SimulationRun
from threats.models import SecurityControl

from .models import ACTIVE_STATUSES, CLOSED_STATUSES, ActivityKind, RemediationActivity, RemediationItem

logger = logging.getLogger("codeguard.remediation")


class RemediationError(ValueError):
    """A request that cannot be turned into a remediation item."""


# Who can see and do what -----------------------------------------------------


def items_for(user):
    """Every item ``user`` may see."""
    workspace = workspace_of(user)
    return RemediationItem.objects.filter(
        Q(owner=user) | Q(workspace=workspace, assignee=user) | Q(workspace=workspace, is_shared=True)
    ).select_related("control", "source_run", "owner", "assignee")


def get_item(user, pk):
    try:
        return items_for(user).get(pk=pk)
    except (RemediationItem.DoesNotExist, ValueError):
        raise Http404("Remediation item not found.") from None


def _same_workspace_admin(user, item):
    return is_admin(user) and workspace_of(user).pk == item.workspace_id


def can_edit(user, item):
    if not can_run_simulations(user):
        return False
    return user.pk in (item.owner_id, item.assignee_id) or _same_workspace_admin(user, item)


def can_assign(user, item):
    return can_run_simulations(user) and (user.pk == item.owner_id or _same_workspace_admin(user, item))


def assignable(workspace):
    """Active members of ``workspace`` whose role lets them act on an item."""
    return (
        members(workspace)
        .filter(is_active=True)
        .filter(Q(profile__role__in=[Role.ADMIN, Role.ANALYST]) | Q(is_superuser=True))
        .order_by("first_name", "last_name", "username")
    )


def _note(item, actor, kind, old="", new="", comment=""):
    return RemediationActivity.objects.create(
        item=item,
        actor=actor,
        actor_username=actor.get_username() if actor else "",
        kind=kind,
        old_value=str(old)[:200],
        new_value=str(new)[:200],
        comment=comment,
    )


def _person(user):
    return (user.get_full_name() or user.get_username()) if user else ""


# Creating and changing items -------------------------------------------------


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
    active = RemediationItem.objects.filter(
        owner=user, scenario_slug=run.scenario_slug, control__slug=control_slug, status__in=ACTIVE_STATUSES
    )
    if active.exists():
        return active.get(), False
    control = SecurityControl.objects.get(slug=control_slug)
    try:
        with transaction.atomic():
            item = RemediationItem.objects.create(
                owner=user,
                workspace=workspace_of(user),
                control=control,
                scenario=run.scenario,
                scenario_slug=run.scenario_slug,
                scenario_name=run.scenario_name,
                source_run=run,
                baseline_risk=run.residual_risk,
                expected_reduction=max(0.0, recommendation["risk_reduction"]),
            )
            _note(item, user, ActivityKind.CREATED)
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
def update(user, item, *, status, note, due_date, evidence_url="", request=None):
    # Read the stored values: a bound ModelForm has already copied the new
    # values onto ``item`` during validation. The row lock serializes
    # concurrent updates so each history entry records the true transition.
    stored = RemediationItem.objects.select_for_update().get(pk=item.pk)
    old_status = stored.status
    item.status = status
    item.note = note
    item.due_date = due_date
    item.evidence_url = evidence_url
    if status in CLOSED_STATUSES and old_status not in CLOSED_STATUSES:
        item.closed_at = timezone.now()
    elif status not in CLOSED_STATUSES:
        item.closed_at = None
    item.save()
    labels = dict(item._meta.get_field("status").choices)
    if old_status != status:
        _note(item, user, ActivityKind.STATUS, labels.get(old_status, old_status), labels.get(status, status))
    if stored.due_date != due_date:
        _note(item, user, ActivityKind.DUE_DATE, stored.due_date or "", due_date or "")
    if stored.evidence_url != evidence_url:
        _note(item, user, ActivityKind.EVIDENCE, stored.evidence_url, evidence_url)
    if stored.note != note:
        _note(item, user, ActivityKind.NOTE)
    record_event(
        user,
        AuditAction.REMEDIATION_UPDATE,
        target=item,
        request=request,
        old_status=old_status,
        new_status=status,
    )
    return item


@transaction.atomic
def assign(user, item, *, assignee, is_shared, request=None):
    """Sets who the item is assigned to and whether the workspace can see it.
    The assignee must be in the item's workspace (``assignable``)."""
    if assignee is not None and not assignable(item.workspace).filter(pk=assignee.pk).exists():
        raise RemediationError("Items can be assigned only to analysts and administrators in this workspace.")
    stored = RemediationItem.objects.select_for_update().get(pk=item.pk)
    changed_assignee = stored.assignee_id != (assignee.pk if assignee else None)
    item.assignee = assignee
    item.is_shared = is_shared
    item.save(update_fields=["assignee", "is_shared", "updated_at"])
    if changed_assignee:
        _note(item, user, ActivityKind.ASSIGNEE, _person(stored.assignee), _person(assignee))
        record_event(
            user,
            AuditAction.REMEDIATION_ASSIGN,
            target=item,
            request=request,
            assignee=assignee.get_username() if assignee else "",
        )
        if assignee is not None and assignee != user and request is not None:
            transaction.on_commit(lambda: _email_assignee(request, item, assignee, user))
    if stored.is_shared != is_shared:
        _note(
            item,
            user,
            ActivityKind.SHARING,
            "Workspace" if stored.is_shared else "Owner and assignee",
            "Workspace" if is_shared else "Owner and assignee",
        )
    return item


def _email_assignee(request, item, assignee, by):
    if not assignee.email or not delivers_email() or not preferences_for(assignee).notify_remediation_due:
        return
    sent = emails.send(
        "remediation_assigned",
        assignee.email,
        {
            "user": assignee,
            "by": _person(by),
            "item": item,
            "link": emails.absolute(request, reverse("remediation:detail", args=[item.pk])),
        },
    )
    if not sent:
        logger.warning("assignment email not sent item=%s", item.pk)


def comment(user, item, text, request=None):
    entry = _note(item, user, ActivityKind.COMMENT, comment=text)
    record_event(user, AuditAction.REMEDIATION_COMMENT, target=item, request=request)
    return entry


# Reading ------------------------------------------------------------------------


def verification(item):
    """The latest completed run of the same scenario by the owner or the
    assignee, made after the item was created, with the control enabled; or None."""
    people = [pk for pk in (item.owner_id, item.assignee_id) if pk]
    candidates = SimulationRun.objects.filter(
        user_id__in=people,
        scenario_slug=item.scenario_slug,
        status=RunStatus.COMPLETED,
        created_at__gt=item.created_at,
    ).order_by("-created_at")
    for run in candidates[:50]:
        if item.control.slug in run.enabled_controls:
            return run
    return None


def tracked_controls(user, scenario_slug):
    """{control slug: item} for the user's own open and in-progress items on a scenario."""
    items = RemediationItem.objects.filter(
        owner=user, scenario_slug=scenario_slug, status__in=ACTIVE_STATUSES
    ).select_related("control")
    return {item.control.slug: item for item in items}
