import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordChangeView, PasswordResetConfirmView, PasswordResetView
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from audit.models import AuditAction, AuditEvent
from audit.services import client_ip, record_event

from . import closure, emails, invitations, lifecycle
from .forms import AcceptInvitationForm, EmailForm, InvitationForm, RegistrationForm, RoleForm, UserFilterForm
from .models import AccountOrigin, Invitation, Profile, Role
from .permissions import admin_required, get_role, registration_open
from .preferences import page_size, preferences_for
from .settings_views import settings_nav
from .throttling import recent_events
from .tokens import email_fingerprint, read_token

logger = logging.getLogger("codeguard.accounts")

SIGNUP_IP_LIMIT = (5, 60)  # sign-up submissions per client IP per hour
CHECK_EMAIL_SESSION_KEY = "cg_check_email"
INVITE_LINK_SESSION_KEY = "cg_invitation_link"


# --- Sign-up and email confirmation ----------------------------------------------


def register(request):
    if request.user.is_authenticated:
        return redirect("core:start")
    if not registration_open():
        return render(request, "registration/register_closed.html", status=403)
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.is_bot:
            # Same outcome as a real sign-up, so the bot learns nothing.
            return _show_check_email(request, form.cleaned_data["email"])
        limit, minutes = SIGNUP_IP_LIMIT
        ip = client_ip(request)
        if ip and recent_events(AuditAction.SIGNUP_REQUEST, minutes, ip_address=ip) >= limit:
            form.add_error(None, "Too many sign-up attempts from your network. Try again in an hour.")
            return render(request, "registration/register.html", {"form": form})
        email = form.cleaned_data["email"]
        record_event(None, AuditAction.SIGNUP_REQUEST, request=request, email_hash=email_fingerprint(email))
        _create_signup_account(request, form, email)
        return _show_check_email(request, email)
    return render(request, "registration/register.html", {"form": form})


def _create_signup_account(request, form, email):
    """Create the account and email a confirmation link. If the address is
    already registered, email its owner instead; the page shown is the same
    either way, so the form does not reveal which addresses have accounts."""
    User = get_user_model()
    existing = User.objects.filter(email__iexact=email).first()
    if existing is None:
        try:
            with transaction.atomic():
                user = form.save()  # the post_save signal creates the profile with the default role
                Profile.objects.filter(user=user).update(origin=AccountOrigin.SIGNUP)
        except IntegrityError:  # another sign-up took the address a moment ago
            existing = User.objects.filter(email__iexact=email).first()
        else:
            user.refresh_from_db()
            record_event(user, AuditAction.REGISTER, target=user, request=request, role=get_role(user))
            lifecycle.send_confirmation(request, user, email)
            return
    if existing is not None:
        emails.send(
            "signup_existing",
            email,
            {
                "email": email,
                "login_link": emails.absolute(request, reverse("accounts:login")),
                "reset_link": emails.absolute(request, reverse("accounts:password_reset")),
            },
        )


def _show_check_email(request, email):
    request.session[CHECK_EMAIL_SESSION_KEY] = email
    return redirect("accounts:check_email")


def check_email(request):
    return render(
        request,
        "registration/check_email.html",
        {
            "email": request.session.get(CHECK_EMAIL_SESSION_KEY),
            "verification_hours": settings.CODEGUARD_EMAIL_VERIFICATION_HOURS,
        },
    )


def verify_email(request, token):
    """GET shows a confirm button and POST applies it, so mail scanners that
    open links automatically cannot use up the token."""
    found = read_token(token)
    if found is None:
        return render(request, "registration/verify_email.html", {"invalid": True}, status=400)
    user, email = found
    if request.method == "POST":
        try:
            changed = lifecycle.confirm(request, user, email)
        except lifecycle.EmailTaken:
            messages.error(request, "That address is now used by another account, so it could not be confirmed.")
            return redirect("settings:account" if request.user.is_authenticated else "accounts:login")
        request.session.pop(CHECK_EMAIL_SESSION_KEY, None)
        if changed:
            messages.success(request, f"Your email address is now {email}.")
        else:
            messages.success(request, "Your email address is confirmed.")
        if request.user.is_authenticated:
            return redirect("settings:account")
        messages.info(request, "You can sign in now.")
        return redirect("accounts:login")
    return render(request, "registration/verify_email.html", {"email": email, "account": user})


def resend_verification(request):
    """Send a new confirmation link. The response is the same whether or not
    the address belongs to an account that needs one."""
    form = EmailForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if lifecycle.over_limit(AuditAction.VERIFICATION_SENT, request, email):
            logger.warning("confirmation resend limited ip=%s", client_ip(request) or "-")
        else:
            user = (
                get_user_model()
                .objects.select_related("profile")
                .filter(email__iexact=email, is_active=True, profile__email_verified_at__isnull=True)
                .first()
            )
            if user is not None:
                lifecycle.send_confirmation(request, user, email)
        return _show_check_email(request, email)
    return render(request, "registration/resend_verification.html", {"form": form})


# --- Invitations ------------------------------------------------------------------


def accept_invitation(request, token):
    invitation = invitations.find(token)
    if invitation is None:
        return render(request, "registration/invitation.html", {"invalid": True}, status=400)
    if request.user.is_authenticated:
        return render(request, "registration/invitation.html", {"signed_in": True, "invitation": invitation})
    form = AcceptInvitationForm(request.POST or None, invitation=invitation)
    if request.method == "POST" and form.is_valid():
        try:
            user = invitations.accept(request, invitation, form.cleaned_data)
        except invitations.AddressTaken:
            form.add_error(None, "An account with this email address already exists. Sign in or reset its password.")
        except IntegrityError:
            form.add_error("username", "This username is taken. Choose another.")
        else:
            if user is None:
                return render(request, "registration/invitation.html", {"invalid": True}, status=400)
            login(request, user, backend="accounts.backends.UsernameOrEmailBackend")
            messages.success(request, f"Welcome to CodeGuard, {user.first_name or user.get_username()}.")
            return redirect("core:start")
    return render(request, "registration/invitation.html", {"form": form, "invitation": invitation})


# --- Passwords ----------------------------------------------------------------------


class AuditedPasswordChangeView(PasswordChangeView):
    template_name = "settings/password.html"
    success_url = reverse_lazy("settings:security")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "settings_page": "security",
            "settings_groups": settings_nav(self.request.user),
        }

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(self.request.user, AuditAction.PASSWORD_CHANGE, request=self.request)
        lifecycle.notify_password_changed(self.request, self.request.user)
        messages.success(self.request, "Your password has been changed.")
        return response


class LimitedPasswordResetView(PasswordResetView):
    """Django's reset view with per-address and per-IP limits. The response
    is identical whether the address is known, unknown or limited."""

    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        email = form.cleaned_data["email"].strip().lower()
        if lifecycle.over_limit(AuditAction.PASSWORD_RESET_REQUEST, self.request, email):
            logger.warning("password reset limited ip=%s", client_ip(self.request) or "-")
            return redirect(self.get_success_url())
        record_event(
            None, AuditAction.PASSWORD_RESET_REQUEST, request=self.request, email_hash=email_fingerprint(email)
        )
        return super().form_valid(form)


class AuditedPasswordResetConfirmView(PasswordResetConfirmView):
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        lifecycle.mark_verified_by_reset(user)
        record_event(user, AuditAction.PASSWORD_RESET, target=user, request=self.request)
        lifecycle.notify_password_changed(self.request, user)
        return response


# --- User management (administrators) -------------------------------------------------


def _admin_context(request, page, **extra):
    return {"settings_page": page, "settings_groups": settings_nav(request.user), **extra}


@admin_required
def user_list(request):
    User = get_user_model()
    filters = UserFilterForm(request.GET or None)
    users = User.objects.select_related("profile").order_by("username")
    if filters.is_valid():
        q = filters.cleaned_data["q"].strip()
        if q:
            users = users.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        role = filters.cleaned_data["role"]
        if role == Role.ADMIN:
            users = users.filter(Q(profile__role=Role.ADMIN) | Q(is_superuser=True))
        elif role:
            users = users.filter(profile__role=role, is_superuser=False)
        status = filters.cleaned_data["status"]
        if status == "active":
            users = users.filter(is_active=True)
        elif status == "suspended":
            users = users.filter(is_active=False)
        elif status == "unverified":
            users = users.filter(profile__email_verified_at__isnull=True)
    page = Paginator(users, page_size(request)).get_page(request.GET.get("page"))
    for user in page:
        user.codeguard_role = get_role(user)
    return render(
        request,
        "settings/users.html",
        _admin_context(
            request,
            "users",
            page_obj=page,
            roles=Role.choices,
            filters=filters,
            invite_form=InvitationForm(),
            invitations=Invitation.objects.filter(accepted_at__isnull=True, revoked_at__isnull=True).select_related(
                "invited_by"
            ),
            invitation_link=request.session.pop(INVITE_LINK_SESSION_KEY, None),
            invitation_days=settings.CODEGUARD_INVITATION_DAYS,
        ),
    )


@admin_required
def user_detail(request, user_id):
    target = get_object_or_404(get_user_model().objects.select_related("profile"), pk=user_id)
    profile, _ = Profile.objects.get_or_create(user=target)
    return render(
        request,
        "settings/user_detail.html",
        _admin_context(
            request,
            "users",
            target=target,
            profile=profile,
            target_role=get_role(target),
            roles=Role.choices,
            can_manage=target != request.user and not target.is_superuser,
            deletion_date=closure.deletion_date(profile),
            events=AuditEvent.objects.filter(Q(actor=target) | Q(object_type="User", object_id=str(target.pk)))[:25],
        ),
    )


def _manageable(request, user_id):
    """The target of a suspend/reactivate/role action, or a redirect explaining why not."""
    target = get_object_or_404(get_user_model(), pk=user_id)
    if target == request.user:
        messages.error(request, "You cannot change your own account here; ask another administrator.")
        return target, redirect("settings:user_detail", target.pk)
    if target.is_superuser:
        messages.error(request, "Superuser accounts are managed with manage.py, not from CodeGuard.")
        return target, redirect("settings:user_detail", target.pk)
    return target, None


@admin_required
@require_POST
def suspend_user(request, user_id):
    target, refused = _manageable(request, user_id)
    if refused:
        return refused
    if target.is_active:
        target.is_active = False
        target.save(update_fields=["is_active"])
        # Ends every session of the account on its next request (SessionEpochMiddleware).
        preferences = preferences_for(target)
        preferences.session_epoch += 1
        preferences.save(update_fields=["session_epoch", "updated_at"])
        record_event(request.user, AuditAction.USER_SUSPEND, target=target, request=request)
    messages.success(request, f"{target.get_username()} is suspended and signed out everywhere.")
    return redirect("settings:user_detail", target.pk)


@admin_required
@require_POST
def reactivate_user(request, user_id):
    target, refused = _manageable(request, user_id)
    if refused:
        return refused
    if not target.is_active:
        target.is_active = True
        target.save(update_fields=["is_active"])
        closure.reopen(target)  # cancels a pending deletion if the owner had closed the account
        record_event(request.user, AuditAction.USER_REACTIVATE, target=target, request=request)
    messages.success(request, f"{target.get_username()} can sign in again.")
    return redirect("settings:user_detail", target.pk)


@admin_required
@require_POST
def send_password_reset(request, user_id):
    """Email the user a reset link. The administrator never sees a password."""
    target = get_object_or_404(get_user_model(), pk=user_id, is_active=True)
    if not target.email:
        messages.error(request, "This account has no email address.")
        return redirect("settings:user_detail", target.pk)
    form = PasswordResetForm({"email": target.email})
    form.is_valid()
    form.save(
        request=request,
        use_https=request.is_secure(),
        email_template_name="registration/password_reset_email.txt",
        subject_template_name="registration/password_reset_subject.txt",
    )
    record_event(
        request.user, AuditAction.PASSWORD_RESET_REQUEST, target=target, request=request,
        email_hash=email_fingerprint(target.email), by_admin=True,
    )  # fmt: skip
    messages.success(request, f"A password reset link was sent to {target.email}.")
    return redirect("settings:user_detail", target.pk)


@admin_required
@require_POST
def change_role(request, user_id):
    target = get_object_or_404(get_user_model(), pk=user_id)
    back = request.POST.get("next") == "detail"
    destination = redirect("settings:user_detail", target.pk) if back else redirect("settings:users")
    form = RoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid role.")
        return destination
    if target == request.user:
        messages.error(request, "You cannot change your own role; ask another administrator.")
        return destination
    if target.is_superuser:
        messages.error(request, "Superuser accounts are always administrators.")
        return destination

    new_role = form.cleaned_data["role"]
    with transaction.atomic():
        profile, _ = Profile.objects.select_for_update().get_or_create(user=target)
        old_role = profile.role
        if old_role != new_role:
            profile.role = new_role
            profile.save(update_fields=["role", "updated_at"])
            record_event(
                request.user,
                AuditAction.ROLE_CHANGE,
                target=target,
                request=request,
                old_role=old_role,
                new_role=new_role,
            )
    messages.success(request, f"{target.get_username()} is now {Role(new_role).label}.")
    return destination


@admin_required
@require_POST
def invite(request):
    form = InvitationForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("settings:users")
    invitation, link, sent = invitations.create(request, form.cleaned_data["email"], form.cleaned_data["role"])
    _report_invitation(request, invitation, link, sent)
    return redirect("settings:users")


@admin_required
@require_POST
def resend_invitation(request, invitation_id):
    invitation = get_object_or_404(Invitation, pk=invitation_id, accepted_at__isnull=True, revoked_at__isnull=True)
    link, sent = invitations.resend(request, invitation)
    _report_invitation(request, invitation, link, sent)
    return redirect("settings:users")


@admin_required
@require_POST
def revoke_invitation(request, invitation_id):
    invitation = get_object_or_404(Invitation, pk=invitation_id, accepted_at__isnull=True, revoked_at__isnull=True)
    invitations.revoke(request, invitation)
    messages.success(request, f"The invitation for {invitation.email} was revoked; its link no longer works.")
    return redirect("settings:users")


def _report_invitation(request, invitation, link, sent):
    # The link is shown once on the next page (and kept only in this session
    # until then) so it can be passed on by hand if email is not delivered.
    request.session[INVITE_LINK_SESSION_KEY] = {"email": invitation.email, "link": link, "sent": sent}
    if sent:
        messages.success(request, f"Invitation sent to {invitation.email}.")
    else:
        messages.warning(
            request,
            f"The invitation for {invitation.email} was not emailed (email is not set up, or sending failed). "
            "Copy the link below and send it yourself.",
        )
