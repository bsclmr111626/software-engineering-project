from django.contrib import admin

from .models import RemediationItem


@admin.register(RemediationItem)
class RemediationItemAdmin(admin.ModelAdmin):
    list_display = ("control", "scenario_name", "owner", "status", "due_date", "created_at")
    list_filter = ("status",)
    search_fields = ("scenario_name", "control__name", "owner__username")
    raw_id_fields = ("owner", "source_run", "scenario")
