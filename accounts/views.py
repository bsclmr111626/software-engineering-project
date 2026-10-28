from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from audit.models import AuditAction
from audit.services import record_event

from .forms import RegistrationForm, RoleForm
from .models import Profile, Role
from .permissions import admin_required, get_role, registration_open
from .preferences import page_size
from .settings_views import settings_nav


def register(request):
    if request.user.is_authenticated:
        return redirect("core:start")
    if not registration_open():
        return render(request, "registration/register_closed.html", status=403)
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()  # the post_save signal assigns the default role
        record_event(user, AuditAction.REGISTER, target=user, request=request, role=get_role(user))
        login(request, user)
        messages.success(request, f"Welcome to CodeGuard, {user.get_username()}. Your account has been created.")
        return redirect("core:dashboard")
    return render(request, "registration/register.html", {"form": form})


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
        messages.success(self.request, "Your password has been changed.")
        return response


@admin_required
def user_list(request):
    users = get_user_model().objects.select_related("profile").order_by("username")
    page = Paginator(users, page_size(request)).get_page(request.GET.get("page"))
    for user in page:
        user.codeguard_role = get_role(user)
    return render(
        request,
        "settings/users.html",
        {
            "page_obj": page,
            "roles": Role.choices,
            "settings_page": "users",
            "settings_groups": settings_nav(request.user),
        },
    )


@admin_required
@require_POST
def change_role(request, user_id):
    target = get_object_or_404(get_user_model(), pk=user_id)
    form = RoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid role.")
        return redirect("settings:users")
    if target == request.user:
        messages.error(request, "You cannot change your own role; ask another administrator.")
        return redirect("settings:users")
    if target.is_superuser:
        messages.error(request, "Superuser accounts are always administrators.")
        return redirect("settings:users")

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
    return redirect("settings:users")
