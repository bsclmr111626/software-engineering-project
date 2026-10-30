from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("start/", views.start, name="start"),
    path("overview/", views.dashboard, name="dashboard"),
    path("overview/risk-distribution.png", views.dashboard_chart, name="dashboard_chart"),
    path("dashboard/", views.dashboard_redirect, name="dashboard_legacy"),
    path("supply-chain/", views.supply_chain, name="supply_chain"),
    path("supply-chain/<slug:key>/", views.stage_detail, name="stage_detail"),
    path("risk/", views.risk, name="risk"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read, name="notifications_read"),
    path("help/", views.methodology, name="help"),
    path("healthz/", views.healthz, name="healthz"),
]
