from django.urls import path

from . import settings_views as views
from . import views as account_views

app_name = "settings"

urlpatterns = [
    path("", views.index, name="index"),
    path("profile/", views.profile, name="profile"),
    path("account/", views.account, name="account"),
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
    path("users/<int:user_id>/role/", account_views.change_role, name="change_role"),
]
