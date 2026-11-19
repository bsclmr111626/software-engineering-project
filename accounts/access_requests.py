"""Access requests: how someone outside CodeGuard asks for an account when
self-registration is closed.

A visitor fills in the public Request access form. The request waits for a
site administrator (a superuser), who sees it in their notifications and in
Settings > Access requests. Approving it creates an ordinary invitation, into
a new workspace for the person's organization or into an existing one, so the
person still sets their own password from the invitation link. Declining it
just closes it.

The form never says whether an address already has an account or a request
waiting: every submission ends on the same "request received" page.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from core.email import delivers_email

from . import emails, invitations
from .models import AccessRequest, AccessRequestStatus, Role, Workspace
from .tokens import email_fingerprint

IP_LIMIT = (5, 60)  # requests per client IP per hour


class AlreadyReviewed(Exception):
    """Someone else approved or declined the request a moment ago."""


class AccountExists(Exception):
    """The address got an account (by sign-up or another invitation) since the request."""


def pending():
    return AccessRequest.objects.filter(status=AccessRequestStatus.PENDING)


def reviewers():
    """Who reviews access requests: active site administrators."""
    return get_user_model().objects.filter(is_superuser=True, is_active=True)


def has_account(email):
    return get_user_model().objects.filter(email__iexact=email).exists()


def submit(request, data):
    """Store a request from AccessRequestForm data. A second request from an
    address that already has one waiting adds nothing (the first is kept).
    Returns the request."""
    email = data["email"].strip().lower()
    existing = pending().filter(email__iexact=email).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            access = AccessRequest.objects.create(
                name=data["name"].strip(),
                email=email,
                organization=data["organization"].strip(),
                reason=data.get("reason", "").strip(),
            )
    except IntegrityError:  # the same address submitted twice at once
        return pending().filter(email__iexact=email).first()
    # The audit log keeps a keyed hash of the address, not the address.
    record_event(None, AuditAction.ACCESS_REQUEST, target=access, request=request, email_hash=email_fingerprint(email))
    transaction.on_commit(lambda: _tell_reviewers(request, access))
    return access


def _tell_reviewers(request, access):
    if not delivers_email():
        return  # the in-app notification still shows it
    link = emails.absolute(request, reverse("settings:access_requests"))
    for reviewer in reviewers().exclude(email=""):
        emails.send(
            "access_request",
            reviewer.email,
            {"access": access, "link": link, "reviewer": reviewer.get_full_name() or reviewer.get_username()},
        )


def approve(request, access, *, role, workspace=None, workspace_name=""):
    """Invite the person into ``workspace``, or into a new workspace called
    ``workspace_name``. Returns (invitation, link, sent) like
    invitations.create, so the link can be passed on by hand."""
    with transaction.atomic():
        locked = AccessRequest.objects.select_for_update().get(pk=access.pk)
        if not locked.is_pending:
            raise AlreadyReviewed
        if has_account(locked.email):
            raise AccountExists
        if workspace is None:
            workspace = Workspace.objects.create(name=workspace_name.strip()[:80], created_by=request.user)
            record_event(
                request.user, AuditAction.WORKSPACE_CREATE, target=workspace, request=request, workspace=workspace
            )
        locked.status = AccessRequestStatus.APPROVED
        locked.reviewed_at = timezone.now()
        locked.reviewed_by = request.user
        locked.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    invitation, link, sent = invitations.create(request, locked.email, role, workspace=workspace)
    locked.invitation = invitation
    locked.save(update_fields=["invitation"])
    record_event(
        request.user,
        AuditAction.ACCESS_APPROVE,
        target=locked,
        request=request,
        workspace=workspace,
        role=Role(role).value,
        workspace_name=workspace.name,
    )
    return invitation, link, sent


def decline(request, access):
    with transaction.atomic():
        locked = AccessRequest.objects.select_for_update().get(pk=access.pk)
        if not locked.is_pending:
            raise AlreadyReviewed
        locked.status = AccessRequestStatus.DECLINED
        locked.reviewed_at = timezone.now()
        locked.reviewed_by = request.user
        locked.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    record_event(request.user, AuditAction.ACCESS_DECLINE, target=locked, request=request)
    return locked


def due_for_deletion(days=None):
    """Reviewed requests older than the retention period. Waiting ones stay."""
    days = settings.CODEGUARD_ACCESS_REQUEST_DAYS if days is None else days
    cutoff = timezone.now() - timedelta(days=days)
    return AccessRequest.objects.exclude(status=AccessRequestStatus.PENDING).filter(reviewed_at__lt=cutoff)
