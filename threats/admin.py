from django.contrib import admin

from .models import PropagationRule, ScenarioControl, SecurityControl, SupplyChainStage, ThreatScenario


class PropagationRuleInline(admin.TabularInline):
    model = PropagationRule
    extra = 0


class ScenarioControlInline(admin.TabularInline):
    model = ScenarioControl
    extra = 0


@admin.register(SupplyChainStage)
class SupplyChainStageAdmin(admin.ModelAdmin):
    list_display = ("position", "name", "key", "weight")


@admin.register(SecurityControl)
class SecurityControlAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "effectiveness", "effort", "priority")
    list_filter = ("category", "effort", "priority")
    filter_horizontal = ("stages",)


@admin.register(ThreatScenario)
class ThreatScenarioAdmin(admin.ModelAdmin):
    list_display = ("name", "initial_stage", "visibility", "status", "is_system", "version", "owner")
    list_filter = ("visibility", "status", "is_system", "initial_stage")
    search_fields = ("name", "slug")
    inlines = [PropagationRuleInline, ScenarioControlInline]

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)
