
from django.urls import path

from . import views


app_name = "code_scans"

urlpatterns = [
    path("", views.scan_list, name="list"),
    path("upload/", views.scan_upload, name="upload"),
    path("<uuid:scan_id>/", views.scan_detail, name="detail"),
]
