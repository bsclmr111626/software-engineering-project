from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "action", "object_type", "object_repr", "ip_address")
    list_filter = ("action",)
    search_fields = ("actor_username", "object_repr")

    # Audit records are read-only, even in the admin site.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
