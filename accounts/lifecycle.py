"""Email confirmation and security notices: the steps shared by sign-up,
email change, password reset and the account page.

Rate limits are counted from the audit log, like sign-in throttling, so they
hold across worker processes without a cache server. Addresses are counted by
a keyed fingerprint (tokens.email_fingerprint), never stored in the log.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditAction
from audit.services import client_ip, record_event

from . import emails
from .throttling import recent_events
from .tokens import email_fingerprint, make_token

# (count, minutes) per address and per client IP.
EMAIL_LIMIT = (3, 60)
IP_LIMIT = (10, 60)


def mask_email(email):
    """ "alice@example.com" -> "a***@example.com", for messages to someone else."""
    local, _, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def over_limit(action, request, email):
    per_email, minutes = EMAIL_LIMIT
    per_ip, ip_minutes = IP_LIMIT
    if recent_events(action, minutes, metadata__email_hash=email_fingerprint(email)) >= per_email:
        return True
    ip = client_ip(request)
    return bool(ip) and recent_events(action, ip_minutes, ip_address=ip) >= per_ip


def send_confirmation(request, user, email):
    """Email a confirmation link for ``email`` (the account's address or its
    pending new address). Returns False if the message could not be sent."""
    link = emails.absolute(request, reverse("accounts:verify_email", args=[make_token(user, email)]))
    sent = emails.send(
        "verify_email",
        email,
        {"user": user, "email": email, "link": link, "hours": settings.CODEGUARD_EMAIL_VERIFICATION_HOURS},
    )
    if sent:
        record_event(
            user,
            AuditAction.VERIFICATION_SENT,
            target=user,
            request=request,
            email_hash=email_fingerprint(email),
            purpose="change" if email != (user.email or "").lower() else "confirm",
        )
    return sent


class EmailTaken(Exception):
    pass


def confirm(request, user, email):
    """Apply a confirmed address: mark the current address verified, or make
    the pending address the account's address. Raises EmailTaken if another
    account claimed the address in the meantime."""
    profile = user.profile
    now = timezone.now()
    try:
        with transaction.atomic():
            if email == (user.email or "").lower():
                profile.email_verified_at = profile.email_verified_at or now
                profile.save(update_fields=["email_verified_at", "updated_at"])
                changed = False
            else:
                user.email = email
                user.save(update_fields=["email"])
                profile.pending_email = ""
                profile.email_verified_at = now
                profile.save(update_fields=["pending_email", "email_verified_at", "updated_at"])
                changed = True
    except IntegrityError:
        raise EmailTaken from None
    record_event(user, AuditAction.EMAIL_VERIFIED, target=user, request=request)
    if changed:
        record_event(user, AuditAction.EMAIL_CHANGE, target=user, request=request, confirmed=True)
    return changed


def mark_verified_by_reset(user):
    """A password reset link is sent to user.email, so using it proves the
    address too. Self-registered accounts that never confirmed can recover."""
    profile = user.profile
    if profile.email_verified_at is None and user.email:
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified_at", "updated_at"])


def notify_password_changed(request, user):
    if not user.email:
        return False
    return emails.send(
        "password_changed",
        user.email,
        {
            "user": user,
            "when": timezone.now(),
            "reset_link": emails.absolute(request, reverse("accounts:password_reset")),
        },
    )
