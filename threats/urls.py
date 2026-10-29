from django.urls import path

from . import views

app_name = "threats"

urlpatterns = [
    path("", views.scenario_list, name="list"),
    path("new/", views.scenario_create, name="create"),
    path("controls/", views.control_list, name="controls"),
    path("controls/<slug:slug>/", views.control_detail, name="control_detail"),
    path("<slug:slug>/", views.scenario_detail, name="detail"),
    path("<slug:slug>/edit/", views.scenario_edit, name="edit"),
    path("<slug:slug>/archive/", views.scenario_archive, name="archive"),
    path("<slug:slug>/delete/", views.scenario_delete, name="delete"),
    path("<slug:slug>/clone/", views.scenario_clone, name="clone"),
]
