from django.urls import path

from . import views

app_name = "remediation"

urlpatterns = [
    path("", views.plan, name="plan"),
    path("track/", views.track, name="track"),
    path("<int:pk>/", views.detail, name="detail"),
]
