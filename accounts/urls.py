from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from . import views
from .forms import ThrottledAuthenticationForm

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/check-email/", views.check_email, name="check_email"),
    path("confirm-email/resend/", views.resend_verification, name="resend_verification"),
    path("confirm-email/<str:token>/", views.verify_email, name="verify_email"),
    path("invitation/<str:token>/", views.accept_invitation, name="accept_invitation"),
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
    path("password/reset/", views.LimitedPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        views.AuditedPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    # Kept so old links keep working; user management lives in Settings.
    path("users/", RedirectView.as_view(pattern_name="settings:users", permanent=True), name="user_list"),
    path("users/<int:user_id>/role/", views.change_role, name="change_role"),
]
