"""The Reports area: the archive of stored runs, exports and printable
assessment documents. The views live with the simulation app because they
read its models; only the URLs (and the navigation section) are separate."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.history, name="list"),
    path("export.csv", views.export_history, name="export_history"),
    path("<uuid:run_id>/", views.report_document, name="document"),
]
