"""Closing and deleting accounts.

Closing is immediate and reversible: the account becomes inactive, every
session ends, and nothing is deleted. After CODEGUARD_ACCOUNT_DELETION_DAYS
the ``purge_closed_accounts`` command deletes the account and everything it
owns (scenarios, simulation runs and their reports, remediation items,
preferences). Until then an administrator can reactivate it.

Audit events survive deletion with the username they were recorded under,
because the log is the record of what happened on the deployment.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event

from .models import Profile, Role
from .preferences import preferences_for


def refusal(user):
    """Why ``user`` may not close their own account, or None if they may."""
    if user.is_superuser:
        return "Superuser accounts are removed with manage.py, not from CodeGuard."
    profile = getattr(user, "profile", None)
    if profile is not None and profile.role == Role.ADMIN:
        others = (
            Profile.objects.filter(role=Role.ADMIN, user__is_active=True).exclude(user=user).exists()
            or get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists()
        )
        if not others:
            return "You are the only administrator. Make someone else an administrator first."
    return None


def owned_counts(user):
    """What deletion will remove, shown before the person confirms."""
    return {
        "runs": user.simulation_runs.count(),
        "shared_runs": user.simulation_runs.filter(is_shared=True).count(),
        "scenarios": user.scenarios.count(),
        "remediation": user.remediation_items.count(),
    }


def deletion_date(profile):
    if profile.closed_at is None:
        return None
    return profile.closed_at + timedelta(days=settings.CODEGUARD_ACCOUNT_DELETION_DAYS)


def close(request, user):
    with transaction.atomic():
        profile, _ = Profile.objects.select_for_update().get_or_create(user=user)
        profile.closed_at = timezone.now()
        profile.pending_email = ""
        profile.save(update_fields=["closed_at", "pending_email", "updated_at"])
        user.is_active = False
        user.save(update_fields=["is_active"])
        # Ends every session of the account on its next request (SessionEpochMiddleware).
        preferences = preferences_for(user)
        preferences.session_epoch += 1
        preferences.save(update_fields=["session_epoch", "updated_at"])
    record_event(user, AuditAction.ACCOUNT_CLOSE, target=user, request=request)
    return profile


def reopen(user):
    """Called when an administrator reactivates a closed account."""
    Profile.objects.filter(user=user).update(closed_at=None)


def due_for_deletion(days=None):
    days = settings.CODEGUARD_ACCOUNT_DELETION_DAYS if days is None else days
    cutoff = timezone.now() - timedelta(days=days)
    return get_user_model().objects.filter(
        is_active=False, is_superuser=False, profile__closed_at__isnull=False, profile__closed_at__lt=cutoff
    )


def delete_closed(user):
    """Permanently delete one closed account and everything it owns."""
    username = user.get_username()
    counts = owned_counts(user)
    closed_at = user.profile.closed_at
    with transaction.atomic():
        user.delete()
        record_event(
            None,
            AuditAction.ACCOUNT_DELETE,
            username=username,
            closed_at=closed_at.isoformat() if closed_at else "",
            **counts,
        )
    return counts
