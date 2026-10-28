from django.contrib import admin

from .models import PropagationEvent, SimulationRun, SimulationStageResult


class StageResultInline(admin.TabularInline):
    model = SimulationStageResult
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SimulationStageResult._meta.fields]


class EventInline(admin.TabularInline):
    model = PropagationEvent
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in PropagationEvent._meta.fields]


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "scenario_name", "user", "status", "inherent_risk", "residual_risk", "classification")
    list_filter = ("status", "classification", "is_shared")
    search_fields = ("scenario_name", "user__username")
    inlines = [StageResultInline, EventInline]

    def has_change_permission(self, request, obj=None):
        return False  # historical results are immutable
