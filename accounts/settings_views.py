"""The settings center: one page per concern, sharing a settings layout.

Every page edits real data: the user's name and email, their Profile, or
their UserPreference row. Organization and user management are visible to
administrators only and are enforced on the server.
"""

import json
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit.models import AuditAction, AuditEvent
from audit.services import client_ip, record_event
from core.email import delivers_email, describe_backend
from remediation.models import RemediationItem
from simulation.models import SimulationRun
from threats.models import ThreatScenario

from . import closure, emails, lifecycle, two_factor
from . import settings_forms as forms
from .models import ColorMode, Profile, Role, Workspace
from .permissions import admin_required, get_role
from .preferences import (
    SESSION_AGENT_KEY,
    SESSION_EPOCH_KEY,
    SESSION_STARTED_KEY,
    describe_agent,
    preferences_for,
)
from .workspaces import workspace_of

# The settings navigation: (url name, label, icon, admin only). Grouped in the template.
SETTINGS_NAV = [
    ("Personal", [("profile", "Profile", "bi-person"), ("account", "Account", "bi-person-vcard")]),
    (
        "Preferences",
        [
            ("appearance", "Appearance and theme", "bi-circle-half"),
            ("typography", "Text and typography", "bi-fonts"),
            ("display", "Display", "bi-layout-text-window"),
            ("accessibility", "Accessibility", "bi-universal-access"),
            ("notifications", "Notifications", "bi-bell"),
        ],
    ),
    (
        "Security and privacy",
        [
            ("privacy", "Privacy and data", "bi-incognito"),
            ("security", "Password and security", "bi-shield-lock"),
            ("sessions", "Sessions", "bi-laptop"),
        ],
    ),
]
ADMIN_NAV = (
    "Administration",
    [("organization", "Workspace", "bi-buildings"), ("users", "Members and roles", "bi-people")],
)


# Site administrators (superusers) also review access requests from outside any workspace.
ACCESS_NAV_ITEM = ("access_requests", "Access requests", "bi-person-plus")


def settings_nav(user):
    from .permissions import is_admin

    if not is_admin(user):
        return SETTINGS_NAV
    label, items = ADMIN_NAV
    return SETTINGS_NAV + [(label, items + ([ACCESS_NAV_ITEM] if user.is_superuser else []))]


def _render(request, template, page, context=None):
    return render(
        request,
        template,
        {"settings_page": page, "settings_groups": settings_nav(request.user), **(context or {})},
    )


@login_required
def index(request):
    return redirect("settings:profile")


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    form = forms.ProfileForm(request.POST or None, instance=profile_obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_event(request.user, AuditAction.PROFILE_UPDATE, request=request, fields=sorted(form.changed_data))
        messages.success(request, "Your profile has been saved.")
        return redirect("settings:profile")
    stats = {
        "runs": SimulationRun.objects.filter(user=request.user).count(),
        "scenarios": ThreatScenario.objects.filter(owner=request.user).count(),
        "remediation": RemediationItem.objects.filter(owner=request.user).count(),
    }
    return _render(request, "settings/profile.html", "profile", {"form": form, "stats": stats})


@login_required
def account(request):
    """Changing the address is a request: the new address must be confirmed
    with an emailed link before it replaces the old one, and the old address
    is told about the request (accounts/lifecycle.py)."""
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    form = forms.EmailChangeForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        new_email = form.cleaned_data["email"]
        if lifecycle.over_limit(AuditAction.VERIFICATION_SENT, request, new_email):
            messages.error(request, "Too many confirmation emails were sent recently. Try again in an hour.")
            return redirect("settings:account")
        previous_pending = profile.pending_email
        profile.pending_email = new_email
        profile.save(update_fields=["pending_email", "updated_at"])
        if not lifecycle.send_confirmation(request, user, new_email):
            profile.pending_email = previous_pending
            profile.save(update_fields=["pending_email", "updated_at"])
            messages.error(
                request, "We could not send the confirmation email, so your address was not changed. Try again later."
            )
            return redirect("settings:account")
        record_event(user, AuditAction.EMAIL_CHANGE_REQUEST, request=request, had_email=bool(user.email))
        if user.email:
            emails.send(
                "email_change_notice", user.email, {"user": user, "new_email_masked": lifecycle.mask_email(new_email)}
            )
        messages.success(request, f"We sent a confirmation link to {new_email}. Your address changes when you open it.")
        return redirect("settings:account")
    return _render(
        request,
        "settings/account.html",
        "account",
        {"form": form, "role": get_role(user), "profile": profile, "delivers_email": delivers_email()},
    )


@login_required
@require_POST
def send_verification(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    if not user.email or profile.email_verified:
        return redirect("settings:account")
    if lifecycle.over_limit(AuditAction.VERIFICATION_SENT, request, user.email):
        messages.error(request, "Too many confirmation emails were sent recently. Try again in an hour.")
    elif lifecycle.send_confirmation(request, user, user.email.lower()):
        messages.success(request, f"We sent a confirmation link to {user.email}.")
    else:
        messages.error(request, "We could not send the confirmation email. Try again later.")
    return redirect("settings:account")


@login_required
@require_POST
def cancel_email_change(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.pending_email:
        profile.pending_email = ""
        profile.save(update_fields=["pending_email", "updated_at"])
        messages.success(request, "The email change was cancelled; its confirmation link no longer works.")
    return redirect("settings:account")


def _preference_page(form_class, template, page, success):
    @login_required
    def view(request):
        preferences = preferences_for(request.user)
        form = form_class(request.POST or None, instance=preferences)
        if request.method == "POST" and form.is_valid():
            form.save()
            if form.changed_data:
                record_event(
                    request.user,
                    AuditAction.PREFERENCES_UPDATE,
                    request=request,
                    page=page,
                    fields=sorted(form.changed_data),
                )
            messages.success(request, success)
            return redirect(f"settings:{page}")
        return _render(request, template, page, {"form": form})

    view.__name__ = page
    return view


appearance = _preference_page(forms.AppearanceForm, "settings/appearance.html", "appearance", "Appearance saved.")
typography = _preference_page(forms.TypographyForm, "settings/typography.html", "typography", "Text settings saved.")
display = _preference_page(forms.DisplayForm, "settings/display.html", "display", "Display settings saved.")
accessibility = _preference_page(
    forms.AccessibilityForm, "settings/accessibility.html", "accessibility", "Accessibility settings saved."
)
notifications = _preference_page(
    forms.NotificationForm, "settings/notifications.html", "notifications", "Notification settings saved."
)


@login_required
def privacy(request):
    preferences = preferences_for(request.user)
    form = forms.PrivacyForm(request.POST or None, instance=preferences)
    if request.method == "POST" and form.is_valid():
        form.save()
        if form.changed_data:
            record_event(
                request.user,
                AuditAction.PREFERENCES_UPDATE,
                request=request,
                page="privacy",
                fields=sorted(form.changed_data),
            )
        messages.success(request, "Privacy settings saved.")
        return redirect("settings:privacy")
    return _render(
        request,
        "settings/privacy.html",
        "privacy",
        {
            "form": form,
            "shared_count": SimulationRun.objects.filter(user=request.user, is_shared=True).count(),
            "event_count": AuditEvent.objects.filter(actor=request.user).count(),
            "deletion_days": settings.CODEGUARD_ACCOUNT_DELETION_DAYS,
        },
    )


@login_required
def close_account(request):
    """Self-service account closure (accounts/closure.py). The account is
    closed at once and deleted after the waiting period."""
    user = request.user
    refusal = closure.refusal(user)
    form = None if refusal else forms.CloseAccountForm(request.POST or None, user=user)
    if form is not None and request.method == "POST" and form.is_valid():
        closure.close(request, user)
        logout(request)
        messages.success(
            request,
            f"Your account is closed. It will be deleted in {settings.CODEGUARD_ACCOUNT_DELETION_DAYS} days; "
            "until then an administrator can reopen it.",
        )
        return redirect("core:landing")
    return _render(
        request,
        "settings/close_account.html",
        "privacy",
        {
            "form": form,
            "refusal": refusal,
            "counts": closure.owned_counts(user),
            "deletion_days": settings.CODEGUARD_ACCOUNT_DELETION_DAYS,
        },
    )


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value is not None else None)


@login_required
def export_data(request):
    """Everything CodeGuard stores about the signed-in user, as JSON."""
    user = request.user
    preferences = preferences_for(user)
    payload = {
        "exported_at": _iso(timezone.now()),
        "account": {
            "username": user.get_username(),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_joined": _iso(user.date_joined),
            "last_login": _iso(user.last_login),
            "role": get_role(user),
            "job_title": getattr(getattr(user, "profile", None), "job_title", ""),
            "team": getattr(getattr(user, "profile", None), "team", ""),
            "workspace": getattr(workspace_of(user), "name", ""),
            "email_verified_at": _iso(getattr(getattr(user, "profile", None), "email_verified_at", None)),
            "pending_email": getattr(getattr(user, "profile", None), "pending_email", ""),
            "account_origin": getattr(getattr(user, "profile", None), "origin", ""),
            # Whether it is on, never the key or the backup codes.
            "two_step_sign_in": two_factor.enabled(user),
        },
        "preferences": {
            field.name: getattr(preferences, field.name)
            for field in preferences._meta.concrete_fields
            if field.name not in {"id", "user", "notifications_seen_at", "updated_at", "session_epoch"}
        },
        "scenarios": [
            {"slug": s.slug, "name": s.name, "visibility": s.visibility, "status": s.status, "version": s.version}
            for s in ThreatScenario.objects.filter(owner=user)
        ],
        "simulation_runs": [
            {
                "id": str(r.id),
                "scenario": r.scenario_name,
                "status": r.status,
                "shared": r.is_shared,
                "created_at": _iso(r.created_at),
                "inherent_risk": r.inherent_risk,
                "residual_risk": r.residual_risk,
            }
            for r in SimulationRun.objects.filter(user=user)
        ],
        "remediation_items": [
            {
                "control": i.control.name,
                "scenario": i.scenario_name,
                "status": i.status,
                "due_date": _iso(i.due_date),
                "note": i.note,
            }
            for i in RemediationItem.objects.filter(owner=user).select_related("control")
        ],
        "audit_events": [
            {
                "at": _iso(e.created_at),
                "action": e.action,
                "object": e.object_repr,
                "ip_address": e.ip_address,
                "metadata": e.metadata,
            }
            for e in AuditEvent.objects.filter(actor=user)[:5000]
        ],
    }
    record_event(user, AuditAction.DATA_EXPORT, request=request, format="json")
    response = HttpResponse(json.dumps(payload, indent=2, default=str), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="codeguard-my-data-{timezone.now():%Y%m%d}.json"'
    return response


@login_required
def security(request):
    username = request.user.get_username()
    sign_ins = AuditEvent.objects.filter(
        Q(
            actor=request.user,
            action__in=[
                AuditAction.LOGIN,
                AuditAction.LOGOUT,
                AuditAction.PASSWORD_CHANGE,
                AuditAction.EMAIL_CHANGE,
                AuditAction.SESSIONS_REVOKED,
                AuditAction.TWO_FACTOR_ENABLE,
                AuditAction.TWO_FACTOR_DISABLE,
                AuditAction.TWO_FACTOR_FAILED,
                AuditAction.BACKUP_CODES_CREATE,
                AuditAction.BACKUP_CODE_USED,
            ],
        )
        | Q(action=AuditAction.TWO_FACTOR_RESET, object_type="User", object_id=str(request.user.pk))
        | Q(action__in=[AuditAction.LOGIN_FAILED, AuditAction.LOGIN_THROTTLED], metadata__attempted_username=username)
    )[:15]
    last_password_change = (
        AuditEvent.objects.filter(actor=request.user, action=AuditAction.PASSWORD_CHANGE)
        .values_list("created_at", flat=True)
        .first()
    )
    return _render(
        request,
        "settings/security.html",
        "security",
        {
            "events": sign_ins,
            "last_password_change": last_password_change,
            "two_factor": two_factor.device_for(request.user),
            "backup_codes_left": two_factor.backup_codes_left(request.user),
            "lockout_failures": settings.CODEGUARD_LOGIN_MAX_FAILURES,
            "lockout_minutes": settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES,
        },
    )


def _sign_out_other_sessions(request):
    preferences = preferences_for(request.user)
    preferences.session_epoch += 1
    preferences.save(update_fields=["session_epoch", "updated_at"])
    request.session[SESSION_EPOCH_KEY] = preferences.session_epoch  # this session stays signed in


def _show_new_codes(request, codes):
    request.session[two_factor.CODES_KEY] = codes
    return redirect("settings:backup_codes")


@login_required
def two_factor_setup(request):
    """Turning two-step sign-in on. The key lives in the session until a code
    from the app proves it was set up, so an abandoned attempt changes nothing."""
    if two_factor.enabled(request.user):
        return redirect("settings:security")
    secret = request.session.get(two_factor.SETUP_KEY)
    if not secret:
        secret = request.session[two_factor.SETUP_KEY] = two_factor.new_secret()
    form = forms.TwoFactorSetupForm(request.POST or None, user=request.user, secret=secret)
    if request.method == "POST" and form.is_valid():
        _, codes = two_factor.enable(request.user, secret, form.step)
        request.session.pop(two_factor.SETUP_KEY, None)
        _sign_out_other_sessions(request)
        record_event(request.user, AuditAction.TWO_FACTOR_ENABLE, request=request)
        messages.success(request, "Two-step sign-in is on. Your other sessions were signed out.")
        return _show_new_codes(request, codes)
    uri = two_factor.provisioning_uri(request.user, secret)
    return _render(
        request,
        "settings/two_factor_setup.html",
        "security",
        {"form": form, "qr": two_factor.qr_svg(uri), "secret": two_factor.grouped(secret)},
    )


@login_required
def backup_codes(request):
    """Shows newly made backup codes. They stay in the session only until the
    person confirms they saved them."""
    codes = request.session.get(two_factor.CODES_KEY)
    if not codes:
        return redirect("settings:security")
    if request.method == "POST":
        request.session.pop(two_factor.CODES_KEY, None)
        messages.success(request, "Keep those backup codes somewhere safe. Each one works once.")
        return redirect("settings:security")
    return _render(request, "settings/backup_codes.html", "security", {"codes": codes})


@login_required
def backup_codes_download(request):
    codes = request.session.get(two_factor.CODES_KEY)
    if not codes:
        return redirect("settings:security")
    lines = [
        "CodeGuard backup codes",
        f"Account: {request.user.get_username()}",
        f"Made: {timezone.now():%Y-%m-%d %H:%M} UTC",
        "",
        "Each code works once. Use one when you cannot use your authenticator app.",
        "",
        *codes,
        "",
    ]
    response = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="codeguard-backup-codes.txt"'
    response["Cache-Control"] = "no-store"
    return response


@login_required
def two_factor_codes(request):
    """Replaces the backup codes; the old ones stop working."""
    if not two_factor.enabled(request.user):
        return redirect("settings:security")
    form = forms.CurrentPasswordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        codes = two_factor.new_backup_codes(request.user)
        record_event(request.user, AuditAction.BACKUP_CODES_CREATE, request=request)
        return _show_new_codes(request, codes)
    return _render(
        request,
        "settings/two_factor_confirm.html",
        "security",
        {
            "form": form,
            "heading": "Make new backup codes",
            "intro": "Your current backup codes stop working and ten new ones are made. You see them once.",
            "submit": "Make new codes",
            "danger": False,
        },
    )


@login_required
def two_factor_disable(request):
    if not two_factor.enabled(request.user):
        return redirect("settings:security")
    form = forms.CurrentPasswordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        two_factor.disable(request.user)
        record_event(request.user, AuditAction.TWO_FACTOR_DISABLE, request=request)
        messages.success(request, "Two-step sign-in is off. Signing in needs only your password now.")
        return redirect("settings:security")
    return _render(
        request,
        "settings/two_factor_confirm.html",
        "security",
        {
            "form": form,
            "heading": "Turn off two-step sign-in",
            "intro": "Signing in will need only your password. Your authenticator entry and backup codes stop working.",
            "submit": "Turn off",
            "danger": True,
        },
    )


@login_required
def sessions(request):
    started = request.session.get(SESSION_STARTED_KEY)
    return _render(
        request,
        "settings/sessions.html",
        "sessions",
        {
            "started": datetime.fromisoformat(started) if started else None,
            "agent": request.session.get(SESSION_AGENT_KEY) or describe_agent(request.META.get("HTTP_USER_AGENT")),
            "expires": request.session.get_expiry_date(),
            "expires_at_close": settings.SESSION_EXPIRE_AT_BROWSER_CLOSE,
            "session_hours": settings.SESSION_COOKIE_AGE // 3600,
            "ip": client_ip(request),
            "recent_logins": AuditEvent.objects.filter(actor=request.user, action=AuditAction.LOGIN)[:8],
        },
    )


@login_required
@require_POST
def revoke_sessions(request):
    _sign_out_other_sessions(request)
    record_event(request.user, AuditAction.SESSIONS_REVOKED, request=request)
    messages.success(request, "Every other session has been signed out. This one stays signed in.")
    return redirect("settings:sessions")


@login_required
@require_POST
def quick_theme(request):
    """The header's light/dark switch. Saves the choice as the color mode."""
    mode = request.POST.get("mode")
    if mode in (ColorMode.LIGHT, ColorMode.DARK):
        preferences = preferences_for(request.user)
        if preferences.color_mode != mode:
            preferences.color_mode = mode
            preferences.save(update_fields=["color_mode", "updated_at"])
    if request.headers.get("X-Requested-With") == "fetch":
        return HttpResponse(status=204)
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = reverse("core:dashboard")
    return redirect(target)


@admin_required
def organization(request):
    """The administrator's view of their workspace. Deployment-wide settings
    are shown to platform administrators (superusers) only."""
    workspace = workspace_of(request.user)
    form = forms.WorkspaceForm(request.POST or None, instance=workspace)
    if request.method == "POST" and form.is_valid():
        if form.changed_data:
            form.save()
            record_event(request.user, AuditAction.WORKSPACE_UPDATE, target=workspace, request=request)
        messages.success(request, "Workspace name saved.")
        return redirect("settings:organization")
    profiles = Profile.objects.filter(workspace=workspace)
    roles = dict(profiles.values_list("role").annotate(n=Count("id")).order_by())
    deployment = None
    if request.user.is_superuser:
        deployment = {
            "registration": settings.CODEGUARD_REGISTRATION,
            "registration_domains": settings.CODEGUARD_REGISTRATION_DOMAINS,
            "workspace_total": Workspace.objects.count(),
            "account_total": get_user_model().objects.count(),
            "email_backend": describe_backend(),
            "from_email": settings.DEFAULT_FROM_EMAIL,
            "client_ip_source": settings.CODEGUARD_CLIENT_IP_HEADER or "REMOTE_ADDR",
        }
    return _render(
        request,
        "settings/organization.html",
        "organization",
        {
            "form": form,
            "workspace": workspace,
            "lockout_failures": settings.CODEGUARD_LOGIN_MAX_FAILURES,
            "lockout_ip_failures": settings.CODEGUARD_LOGIN_IP_MAX_FAILURES,
            "lockout_minutes": settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES,
            "session_hours": settings.SESSION_COOKIE_AGE // 3600,
            "expires_at_close": settings.SESSION_EXPIRE_AT_BROWSER_CLOSE,
            "user_total": profiles.count(),
            "role_counts": [(label, roles.get(value, 0)) for value, label in Role.choices],
            "deployment": deployment,
        },
    )
