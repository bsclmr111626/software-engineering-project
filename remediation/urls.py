from django.urls import path
from . import views

app_name = "remediation"

urlpatterns = [
    path("", views.plan, name="plan"),
    path("track/", views.track, name="track"),
    path("<int:pk>/", views.detail, name="detail"),

    path(
        "code/<int:pk>/",
        views.code_detail,
        name="code_detail",
    ),
    path(
        "code-finding/<uuid:finding_id>/track/",
        views.track_code_finding,
        name="track_code_finding",
    ),
]