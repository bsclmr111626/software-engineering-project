import uuid

from django.conf import settings
from django.db import models


class RunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class SimulationRun(models.Model):
    """One execution of the simulation engine.

    The run stores a versioned snapshot of every input (``input_snapshot``)
    and the full engine output (``result``). Reports are rendered from these
    stored values only, so editing or deleting the scenario later never
    changes a historical report. ``scenario`` becomes NULL if the scenario is
    deleted; the denormalized name/slug/version fields keep the history readable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="simulation_runs")
    scenario = models.ForeignKey(
        "threats.ThreatScenario", null=True, blank=True, on_delete=models.SET_NULL, related_name="runs"
    )
    scenario_name = models.CharField(max_length=120)
    scenario_slug = models.SlugField(max_length=80)
    scenario_version = models.PositiveIntegerField()
    entry_stage_name = models.CharField(max_length=80)
    status = models.CharField(max_length=10, choices=RunStatus.choices, default=RunStatus.PENDING, db_index=True)
    error_message = models.CharField(max_length=255, blank=True)
    is_shared = models.BooleanField(default=False, help_text="Shared reports are visible read-only to all users.")

    likelihood = models.PositiveSmallIntegerField()
    severity = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    threshold = models.PositiveSmallIntegerField()
    enabled_controls = models.JSONField(default=list, blank=True)

    inherent_risk = models.FloatField(null=True, blank=True)
    residual_risk = models.FloatField(null=True, blank=True)
    classification = models.CharField(max_length=16, blank=True)
    compromised_count = models.PositiveSmallIntegerField(default=0)
    blocked_count = models.PositiveSmallIntegerField(default=0)

    input_snapshot = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["is_shared", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(residual_risk__isnull=True) | models.Q(residual_risk__gte=0, residual_risk__lte=100),
                name="run_residual_risk_range",
            ),
        ]

    def __str__(self):
        return f"{self.scenario_name} @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def short_id(self):
        return str(self.id)[:8]

    @property
    def risk_reduction(self):
        if self.inherent_risk is None or self.residual_risk is None:
            return None
        return round(self.inherent_risk - self.residual_risk, 1)


class SimulationStageResult(models.Model):
    """Per-stage outcome of a run (denormalized for history and querying)."""

    run = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name="stage_results")
    stage_key = models.SlugField(max_length=32)
    stage_name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=16)
    inherent_state = models.CharField(max_length=16)
    inherent_likelihood = models.FloatField()
    residual_likelihood = models.FloatField()
    preventive_coverage = models.FloatField()
    mitigating_coverage = models.FloatField()
    inherent_risk = models.FloatField()
    residual_risk = models.FloatField()
    classification = models.CharField(max_length=16)
    explanation = models.TextField()

    class Meta:
        ordering = ["run", "position"]
        constraints = [models.UniqueConstraint(fields=["run", "stage_key"], name="unique_stage_per_run")]
        indexes = [models.Index(fields=["stage_key", "state"])]

    def __str__(self):
        return f"{self.stage_name}: {self.state}"


class PropagationEvent(models.Model):
    """One evaluated propagation edge in a run."""

    run = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name="events")
    order = models.PositiveSmallIntegerField()
    source_key = models.SlugField(max_length=32)
    source_name = models.CharField(max_length=80)
    target_key = models.SlugField(max_length=32)
    target_name = models.CharField(max_length=80)
    kind = models.CharField(max_length=16)
    base_probability = models.FloatField()
    control_coverage = models.FloatField()
    effective_probability = models.FloatField()
    threshold = models.FloatField()
    outcome = models.CharField(max_length=24)
    target_already_compromised = models.BooleanField(default=False)
    transmitted_likelihood = models.FloatField()
    controls_applied = models.JSONField(default=list, blank=True)
    explanation = models.CharField(max_length=300)

    class Meta:
        ordering = ["run", "order"]
        constraints = [models.UniqueConstraint(fields=["run", "order"], name="unique_event_order_per_run")]

    def __str__(self):
        return f"{self.source_name} -> {self.target_name}: {self.outcome}"
