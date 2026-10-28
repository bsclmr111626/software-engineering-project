"""The settings center: one page per concern, sharing a settings layout.

Every page edits real data: the user's name and email, their Profile, or
their UserPreference row. Organization and user management are visible to
administrators only and are enforced on the server.
"""

import json
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit.models import AuditAction, AuditEvent
from audit.services import record_event
from remediation.models import RemediationItem
from simulation.models import SimulationRun
from threats.models import ThreatScenario

from . import settings_forms as forms
from .models import ColorMode, Profile, Role
from .permissions import admin_required, get_role
from .preferences import (
    SESSION_AGENT_KEY,
    SESSION_EPOCH_KEY,
    SESSION_STARTED_KEY,
    describe_agent,
    preferences_for,
)

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
    [("organization", "Organization", "bi-buildings"), ("users", "Users and roles", "bi-people")],
)


def settings_nav(user):
    from .permissions import is_admin

    return SETTINGS_NAV + ([ADMIN_NAV] if is_admin(user) else [])


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
    form = forms.EmailChangeForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        old = request.user.email
        request.user.email = form.cleaned_data["email"]
        request.user.save(update_fields=["email"])
        record_event(request.user, AuditAction.EMAIL_CHANGE, request=request, had_email=bool(old))
        messages.success(request, "Your email address has been changed.")
        return redirect("settings:account")
    return _render(request, "settings/account.html", "account", {"form": form, "role": get_role(request.user)})


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
            ],
        )
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
            "lockout_failures": settings.CODEGUARD_LOGIN_MAX_FAILURES,
            "lockout_minutes": settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES,
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
            "ip": request.META.get("REMOTE_ADDR"),
            "recent_logins": AuditEvent.objects.filter(actor=request.user, action=AuditAction.LOGIN)[:8],
        },
    )


@login_required
@require_POST
def revoke_sessions(request):
    preferences = preferences_for(request.user)
    preferences.session_epoch += 1
    preferences.save(update_fields=["session_epoch", "updated_at"])
    request.session[SESSION_EPOCH_KEY] = preferences.session_epoch  # this session stays signed in
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
    roles = dict(Profile.objects.values_list("role").annotate(n=Count("id")).order_by())
    return _render(
        request,
        "settings/organization.html",
        "organization",
        {
            "registration": settings.CODEGUARD_REGISTRATION,
            "registration_domains": settings.CODEGUARD_REGISTRATION_DOMAINS,
            "default_role": Role(settings.CODEGUARD_DEFAULT_ROLE).label,
            "lockout_failures": settings.CODEGUARD_LOGIN_MAX_FAILURES,
            "lockout_ip_failures": settings.CODEGUARD_LOGIN_IP_MAX_FAILURES,
            "lockout_minutes": settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES,
            "session_hours": settings.SESSION_COOKIE_AGE // 3600,
            "expires_at_close": settings.SESSION_EXPIRE_AT_BROWSER_CLOSE,
            "user_total": get_user_model().objects.count(),
            "role_counts": [(label, roles.get(value, 0)) for value, label in Role.choices],
            "email_backend": settings.EMAIL_BACKEND.rsplit(".", 1)[-1],
        },
    )
