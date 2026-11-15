from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Profile


def _admin_login(request, extra_context=None):
    """Sends /admin/login/ to CodeGuard's own sign-in, so the admin's sign-in
    page cannot be used to get around the sign-in limits (accounts/throttling.py)
    or two-step sign-in (accounts/two_factor.py). Signed-in staff go straight on."""
    target = request.GET.get(REDIRECT_FIELD_NAME) or reverse("admin:index")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        target = reverse("admin:index")
    if request.user.is_authenticated:
        return redirect(target) if request.user.is_staff else redirect("core:start")
    return redirect(f"{reverse('accounts:login')}?{urlencode({REDIRECT_FIELD_NAME: target})}")


admin.site.login = _admin_login


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
