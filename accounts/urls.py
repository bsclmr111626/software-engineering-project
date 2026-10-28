from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from . import views
from .forms import ThrottledAuthenticationForm

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True, authentication_form=ThrottledAuthenticationForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/change/", views.AuditedPasswordChangeView.as_view(), name="password_change"),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path("password/reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(success_url=reverse_lazy("accounts:password_reset_complete")),
        name="password_reset_confirm",
    ),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    # Kept so old links keep working; user management lives in Settings.
    path("users/", RedirectView.as_view(pattern_name="settings:users", permanent=True), name="user_list"),
    path("users/<int:user_id>/role/", views.change_role, name="change_role"),
]
