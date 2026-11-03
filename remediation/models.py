from django.conf import settings
from django.db import models
from django.db.models import Q


class RemediationStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    DONE = "done", "Done"
    RISK_ACCEPTED = "risk_accepted", "Risk accepted"


ACTIVE_STATUSES = (RemediationStatus.OPEN, RemediationStatus.IN_PROGRESS)
CLOSED_STATUSES = (RemediationStatus.DONE, RemediationStatus.RISK_ACCEPTED)


class RemediationItem(models.Model):
    """A recommended control that an analyst has committed to act on.

    Created from a report's recommendation, so it keeps the run it came from
    and the modeled reduction at that time. Whether the change has been
    verified is derived from later runs (``services.verification``), not
    stored, so it cannot go stale. Like runs, items are private to their owner.
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="remediation_items")
    control = models.ForeignKey("threats.SecurityControl", on_delete=models.PROTECT, related_name="remediation_items")
    scenario = models.ForeignKey(
        "threats.ThreatScenario", null=True, blank=True, on_delete=models.SET_NULL, related_name="remediation_items"
    )
    scenario_slug = models.SlugField(max_length=80)
    scenario_name = models.CharField(max_length=120)
    source_run = models.ForeignKey(
        "simulation.SimulationRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="remediation_items"
    )
    baseline_risk = models.FloatField(help_text="Overall residual risk of the source run.")
    expected_reduction = models.FloatField(help_text="Modeled reduction when the item was created.")
    status = models.CharField(max_length=16, choices=RemediationStatus.choices, default=RemediationStatus.OPEN)
    note = models.TextField(blank=True, max_length=2000)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        indexes = [models.Index(fields=["owner", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "scenario_slug", "control"],
                condition=Q(status__in=["open", "in_progress"]),
                name="one_active_item_per_control_and_scenario",
                violation_error_message="This control is already on your remediation plan for this scenario.",
            ),
            models.CheckConstraint(condition=Q(expected_reduction__gte=0), name="remediation_reduction_non_negative"),
        ]

    def __str__(self):
        return f"{self.control} for {self.scenario_name} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES
