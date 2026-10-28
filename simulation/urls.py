from django.urls import path

from . import views

app_name = "simulation"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("new/", views.configure, name="configure"),
    path("results/", views.results, name="results"),
    path("compare/", views.compare, name="compare"),
    path("compare/chart.png", views.compare_chart, name="compare_chart"),
    path("<uuid:run_id>/", views.detail, name="detail"),
    path("<uuid:run_id>/share/", views.toggle_share, name="share"),
    path("<uuid:run_id>/<slug:section>/", views.detail, name="detail_section"),
    path("<uuid:run_id>/chart/<slug:kind>.png", views.chart, name="chart"),
    path("<uuid:run_id>/export.csv", views.export_run, name="export_run"),
]
