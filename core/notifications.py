"""The in-app notification feed.

Notifications are derived from records that already exist (audit events,
shared reports and remediation due dates) rather than stored separately, so
they can never disagree with the data they describe. Each category can be
switched off in Settings > Notifications; ``notifications_seen_at`` marks
which ones are new.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from accounts.preferences import preferences_for
from audit.models import AuditAction, AuditEvent
from remediation.models import ACTIVE_STATUSES, RemediationItem
from simulation.models import RunStatus, SimulationRun

WINDOW_DAYS = 30
DUE_SOON_DAYS = 7
LIMIT = 30


@dataclass(frozen=True)
class Notification:
    category: str  # "shared_report" | "remediation" | "security"
    icon: str
    title: str
    detail: str
    url: str
    at: datetime
    unread: bool = False


def _shared_reports(user, since):
    events = (
        AuditEvent.objects.filter(action=AuditAction.REPORT_SHARE, created_at__gte=since, metadata__shared=True)
        .exclude(actor=user)
        .order_by("-created_at")[:LIMIT]
    )
    latest = {}
    for event in events:
        latest.setdefault(event.object_id, event)
    runs = SimulationRun.objects.filter(pk__in=list(latest), is_shared=True, status=RunStatus.COMPLETED)
    for run in runs:
        event = latest[str(run.pk)]
        yield Notification(
            "shared_report",
            "bi-share",
            f"{event.actor_username or 'A colleague'} shared a report",
            f"{run.scenario_name}: residual risk {run.residual_risk} ({run.classification})",
            reverse("simulation:detail", args=[run.pk]),
            event.created_at,
        )


def _remediation(user):
    today = timezone.localdate()
    items = RemediationItem.objects.filter(
        owner=user,
        status__in=ACTIVE_STATUSES,
        due_date__isnull=False,
        due_date__lte=today + timedelta(days=DUE_SOON_DAYS),
    ).select_related("control")
    for item in items:
        days = (item.due_date - today).days
        if days < 0:
            title = f"Overdue by {-days} day{'s' if days != -1 else ''}"
        elif days == 0:
            title = "Due today"
        else:
            title = f"Due in {days} day{'s' if days != 1 else ''}"
        at = timezone.make_aware(datetime.combine(min(item.due_date, today), time.min))
        yield Notification(
            "remediation",
            "bi-calendar-event",
            f"{title}: {item.control.name}",
            f"Remediation for {item.scenario_name} is {item.get_status_display().lower()}.",
            reverse("remediation:detail", args=[item.pk]),
            at,
        )


SECURITY_TITLES = {
    AuditAction.PASSWORD_CHANGE: "Your password was changed",
    AuditAction.EMAIL_CHANGE: "Your email address was changed",
    AuditAction.SESSIONS_REVOKED: "Other sessions were signed out",
    AuditAction.ROLE_CHANGE: "Your role was changed",
    AuditAction.LOGIN_FAILED: "Failed sign-in attempt on your account",
    AuditAction.LOGIN_THROTTLED: "Sign-in to your account was temporarily blocked",
}


def _security(user, since):
    own = AuditEvent.objects.filter(
        actor=user,
        action__in=[AuditAction.PASSWORD_CHANGE, AuditAction.EMAIL_CHANGE, AuditAction.SESSIONS_REVOKED],
        created_at__gte=since,
    )
    role = AuditEvent.objects.filter(
        action=AuditAction.ROLE_CHANGE, object_type="User", object_id=str(user.pk), created_at__gte=since
    )
    failed = AuditEvent.objects.filter(
        action__in=[AuditAction.LOGIN_FAILED, AuditAction.LOGIN_THROTTLED],
        metadata__attempted_username=user.get_username(),
        created_at__gte=since,
    )
    for event in (own | role | failed).order_by("-created_at")[:LIMIT]:
        if event.action == AuditAction.ROLE_CHANGE:
            detail = f"Now {event.metadata.get('new_role', 'updated')}, changed by {event.actor_username or 'an administrator'}."
        elif event.action in (AuditAction.LOGIN_FAILED, AuditAction.LOGIN_THROTTLED):
            detail = f"From {event.ip_address or 'an unknown address'}. If this was not you, change your password."
        else:
            detail = f"From {event.ip_address or 'an unknown address'}."
        yield Notification(
            "security",
            "bi-shield-exclamation"
            if event.action in (AuditAction.LOGIN_FAILED, AuditAction.LOGIN_THROTTLED)
            else "bi-shield-check",
            SECURITY_TITLES[event.action],
            detail,
            reverse("settings:security"),
            event.created_at,
        )


def notifications_for(user):
    """Newest first, limited to the categories the user has switched on."""
    preferences = preferences_for(user)
    since = timezone.now() - timedelta(days=WINDOW_DAYS)
    found = []
    if preferences.notify_shared_reports:
        found += _shared_reports(user, since)
    if preferences.notify_remediation_due:
        found += _remediation(user)
    if preferences.notify_account_security:
        found += _security(user, since)
    seen = preferences.notifications_seen_at
    found = [
        Notification(**{**n.__dict__, "unread": seen is None or n.at > seen})
        for n in sorted(found, key=lambda n: n.at, reverse=True)[:LIMIT]
    ]
    return found


def unread_count(user):
    return sum(1 for n in notifications_for(user) if n.unread)
