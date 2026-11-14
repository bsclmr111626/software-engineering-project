from django.urls import path

from . import settings_views as views
from . import views as account_views

app_name = "settings"

urlpatterns = [
    path("", views.index, name="index"),
    path("profile/", views.profile, name="profile"),
    path("account/", views.account, name="account"),
    path("account/confirm-email/", views.send_verification, name="send_verification"),
    path("account/cancel-email-change/", views.cancel_email_change, name="cancel_email_change"),
    path("appearance/", views.appearance, name="appearance"),
    path("appearance/quick/", views.quick_theme, name="quick_theme"),
    path("typography/", views.typography, name="typography"),
    path("display/", views.display, name="display"),
    path("accessibility/", views.accessibility, name="accessibility"),
    path("notifications/", views.notifications, name="notifications"),
    path("privacy/", views.privacy, name="privacy"),
    path("privacy/export.json", views.export_data, name="export_data"),
    path("security/", views.security, name="security"),
    path("sessions/", views.sessions, name="sessions"),
    path("sessions/revoke/", views.revoke_sessions, name="revoke_sessions"),
    path("organization/", views.organization, name="organization"),
    path("users/", account_views.user_list, name="users"),
    path("users/invite/", account_views.invite, name="invite"),
    path("users/invitations/<int:invitation_id>/resend/", account_views.resend_invitation, name="resend_invitation"),
    path("users/invitations/<int:invitation_id>/revoke/", account_views.revoke_invitation, name="revoke_invitation"),
    path("users/<int:user_id>/", account_views.user_detail, name="user_detail"),
    path("users/<int:user_id>/role/", account_views.change_role, name="change_role"),
    path("users/<int:user_id>/suspend/", account_views.suspend_user, name="suspend_user"),
    path("users/<int:user_id>/reactivate/", account_views.reactivate_user, name="reactivate_user"),
    path("users/<int:user_id>/password-reset/", account_views.send_password_reset, name="send_password_reset"),
]
