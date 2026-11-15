"""Workspaces: the boundary for everything people share (see models.Workspace).

``workspace_of`` is the one way to ask which workspace a user belongs to.
Every query that returns shared data filters on it, so an account can never
read another workspace's scenarios, reports, users, invitations or audit
events, whatever ids appear in a URL or a form.
"""

from django.db import transaction

from .models import Profile, Workspace

DEFAULT_NAME = "CodeGuard"


def default_workspace():
    """Where accounts created outside sign-up and invitations are placed
    (createsuperuser, the Django admin, fixtures)."""
    workspace = Workspace.objects.filter(is_default=True).first()
    if workspace is None:
        workspace, _ = Workspace.objects.get_or_create(is_default=True, defaults={"name": DEFAULT_NAME})
    return workspace


def workspace_of(user):
    """The user's workspace, or None for anonymous users."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(user, "_cg_workspace", None)
    if cached is None:
        profile = Profile.objects.select_related("workspace").filter(user=user).first()
        if profile is None:
            profile = Profile.objects.create(user=user, workspace=default_workspace())
        cached = user._cg_workspace = profile.workspace
    return cached


def workspace_id_of(user):
    workspace = workspace_of(user)
    return workspace.pk if workspace is not None else None


def same_workspace(user, other):
    return workspace_id_of(user) is not None and workspace_id_of(user) == workspace_id_of(other)


def members(workspace):
    """Queryset of the workspace's user accounts."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(profile__workspace=workspace)


@transaction.atomic
def create_for(user, name):
    """Create a workspace and move ``user`` into it (used at sign-up)."""
    workspace = Workspace.objects.create(
        name=name.strip()[:80] or f"{user.get_username()}'s workspace", created_by=user
    )
    Profile.objects.filter(user=user).update(workspace=workspace)
    user._cg_workspace = workspace
    return workspace
