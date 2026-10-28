"""Server-side role checks.

Templates may hide buttons for convenience, but every protected view calls
these helpers (or the decorators below), so authorization never depends on
what the browser shows.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Profile, Role


def get_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    try:
        return user.profile.role
    except Profile.DoesNotExist:
        return Role.VIEWER


def is_admin(user):
    return get_role(user) == Role.ADMIN


def can_manage_scenarios(user):
    return get_role(user) in (Role.ADMIN, Role.ANALYST)


def can_run_simulations(user):
    return get_role(user) in (Role.ADMIN, Role.ANALYST)


def registration_open():
    """Whether self-registration is offered at all (CODEGUARD_REGISTRATION)."""
    return settings.CODEGUARD_REGISTRATION != "closed"


def role_required(*roles):
    """Require login and one of ``roles``; otherwise respond 403."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if get_role(request.user) not in roles:
                raise PermissionDenied("Your role does not permit this action.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required(Role.ADMIN)
analyst_required = role_required(Role.ADMIN, Role.ANALYST)
