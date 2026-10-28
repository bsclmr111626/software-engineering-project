"""Sign-in throttling based on the audit log.

Failed sign-ins are already recorded as ``login_failed`` audit events, so the
counts below come from the database. That keeps the limit correct across
several worker processes without adding a cache server.

Two limits apply within a sliding window:

* per username: stops password guessing against one account. Failures before
  that account's last successful sign-in are not counted;
* per client IP: stops one source from spraying many usernames.

A locked username stays locked for the rest of the window even with the right
password, so the response never reveals whether a guess was correct. The
trade-off is that anyone can temporarily lock an account by guessing wrongly;
the lock is short and every attempt is audited.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.models import AuditAction, AuditEvent


def _window_start():
    return timezone.now() - timedelta(minutes=settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES)


def username_failures(username):
    start = _window_start()
    last_success = (
        AuditEvent.objects.filter(action=AuditAction.LOGIN, actor_username__iexact=username)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if last_success and last_success > start:
        start = last_success
    return AuditEvent.objects.filter(
        action=AuditAction.LOGIN_FAILED,
        metadata__attempted_username__iexact=username,
        created_at__gte=start,
    ).count()


def ip_failures(ip_address):
    if not ip_address:
        return 0
    return AuditEvent.objects.filter(
        action=AuditAction.LOGIN_FAILED, ip_address=ip_address, created_at__gte=_window_start()
    ).count()


def is_locked(username, ip_address):
    if username and username_failures(username) >= settings.CODEGUARD_LOGIN_MAX_FAILURES:
        return True
    return ip_failures(ip_address) >= settings.CODEGUARD_LOGIN_IP_MAX_FAILURES
