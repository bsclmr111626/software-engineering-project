from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("threats/", include("threats.urls")),
    path("simulations/", include("simulation.urls")),
    path("remediation/", include("remediation.urls")),
    path("audit/", include("audit.urls")),
    path("admin/", admin.site.urls),
]

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"
