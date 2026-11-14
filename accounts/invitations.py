"""Invitations: how administrators add people without ever handling their
passwords.

The link contains a random 256-bit token; only its SHA-256 hash is stored.
Creating or resending an invitation emails the link and also returns it, so
an administrator can pass it on by hand when email is not configured or
fails. The link is shown once and never logged.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from core.email import delivers_email

from . import emails
from .models import AccountOrigin, Invitation, Profile, Role


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token(invitation):
    token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash(token)
    invitation.expires_at = timezone.now() + timedelta(days=settings.CODEGUARD_INVITATION_DAYS)
    return token


def _deliver(request, invitation, token):
    link = emails.absolute(request, reverse("accounts:accept_invitation", args=[token]))
    inviter = request.user.get_full_name() or request.user.get_username()
    sent = emails.send(
        "invitation",
        invitation.email,
        {"inviter": inviter, "role": Role(invitation.role).label, "link": link, "expires": invitation.expires_at},
    )
    # A console backend "sends" by printing; that is not an email the invitee gets.
    sent = sent and delivers_email()
    if sent:
        invitation.sent_at = timezone.now()
        invitation.save(update_fields=["sent_at"])
    return link, sent


def open_invitation_for(email):
    return Invitation.objects.filter(email__iexact=email, accepted_at__isnull=True, revoked_at__isnull=True).first()


def create(request, email, role):
    """Invite ``email`` with ``role``. An open invitation for the same address
    is reused with a fresh link. Returns (invitation, link, sent)."""
    with transaction.atomic():
        invitation = open_invitation_for(email)
        created = invitation is None
        if created:
            invitation = Invitation(email=email, role=role, invited_by=request.user)
        else:
            invitation.role = role
        token = _new_token(invitation)
        invitation.save()
    record_event(
        request.user,
        AuditAction.INVITATION_CREATE if created else AuditAction.INVITATION_RESEND,
        target=invitation,
        request=request,
        role=role,
    )
    link, sent = _deliver(request, invitation, token)
    return invitation, link, sent


def resend(request, invitation):
    token = _new_token(invitation)
    invitation.save(update_fields=["token_hash", "expires_at"])
    record_event(request.user, AuditAction.INVITATION_RESEND, target=invitation, request=request)
    return _deliver(request, invitation, token)


def revoke(request, invitation):
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    record_event(request.user, AuditAction.INVITATION_REVOKE, target=invitation, request=request)


def find(token):
    """The open invitation for ``token``, or None (unknown, used, revoked or expired)."""
    if not token or len(token) > 100:
        return None
    invitation = Invitation.objects.filter(token_hash=_hash(token)).first()
    return invitation if invitation is not None and invitation.is_open else None


class AddressTaken(Exception):
    pass


def accept(request, invitation, data):
    """Create the invited account from AcceptInvitationForm data. The address
    is confirmed, because the person opened a link sent to it."""
    User = get_user_model()
    with transaction.atomic():
        locked = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if not locked.is_open:
            return None
        if User.objects.filter(email__iexact=locked.email).exists():
            raise AddressTaken
        user = User.objects.create_user(
            username=data["username"],
            email=locked.email.lower(),
            password=data["password1"],
            first_name=data["first_name"].strip(),
            last_name=data.get("last_name", "").strip(),
        )
        Profile.objects.update_or_create(
            user=user,
            defaults={"role": locked.role, "origin": AccountOrigin.INVITATION, "email_verified_at": timezone.now()},
        )
        locked.accepted_at = timezone.now()
        locked.accepted_user = user
        locked.save(update_fields=["accepted_at", "accepted_user"])
    record_event(user, AuditAction.INVITATION_ACCEPT, target=locked, request=request, role=locked.role)
    return user
