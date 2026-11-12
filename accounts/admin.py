from django.contrib import admin

from .forms import ThrottledAdminAuthenticationForm
from .models import Profile

# The admin site has its own sign-in page; give it the same sign-in limits as
# /accounts/login/ (accounts/throttling.py).
admin.site.login_form = ThrottledAdminAuthenticationForm


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
