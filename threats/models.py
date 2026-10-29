from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from simulation.propagation import edge_kind

PERCENT = [MinValueValidator(0), MaxValueValidator(100)]
LEVEL = [MinValueValidator(1), MaxValueValidator(5)]


class SupplyChainStage(models.Model):
    """One of the five ordered stages of the software supply chain."""

    key = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField(unique=True)
    description = models.TextField()
    assets = models.TextField(help_text="Typical assets that live at this stage.")
    icon = models.CharField(max_length=40, help_text="Bootstrap Icons name, e.g. 'laptop'.")
    weight = models.PositiveSmallIntegerField(
        default=1, validators=LEVEL, help_text="Criticality weight used to aggregate overall risk."
    )

    class Meta:
        ordering = ["position"]
        constraints = [models.CheckConstraint(condition=Q(weight__gte=1, weight__lte=5), name="stage_weight_range")]

    def __str__(self):
        return self.name


class ControlCategory(models.TextChoices):
    PREVENTIVE = "preventive", "Preventive"
    DETECTIVE = "detective", "Detective"
    RECOVERY = "recovery", "Recovery"


class Level(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class SecurityControl(models.Model):
    """A reusable mitigation from the control catalog."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField()
    category = models.CharField(max_length=16, choices=ControlCategory.choices)
    stages = models.ManyToManyField(SupplyChainStage, related_name="controls")
    effectiveness = models.PositiveSmallIntegerField(
        validators=PERCENT, help_text="Illustrative model parameter (0-100), not a measured statistic."
    )
    effort = models.CharField(max_length=8, choices=Level.choices)
    priority = models.CharField(max_length=8, choices=Level.choices)
    addresses = models.TextField(help_text="The weakness or propagation path this control addresses.")
    effectiveness_basis = models.TextField(
        blank=True, help_text="The assumption behind the effectiveness value (an illustrative parameter)."
    )
    limitations = models.TextField(blank=True, help_text="What this control does not cover or can be bypassed by.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(effectiveness__lte=100), name="control_effectiveness_range"),
        ]

    def __str__(self):
        return self.name


class Visibility(models.TextChoices):
    SHARED = "shared", "Shared"
    PRIVATE = "private", "Private"


class ScenarioStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ThreatScenario(models.Model):
    """A hypothetical supply chain attack used as simulation input."""

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField()
    initial_stage = models.ForeignKey(SupplyChainStage, on_delete=models.PROTECT, related_name="entry_scenarios")
    likelihood = models.PositiveSmallIntegerField(validators=PERCENT, help_text="Base likelihood (0-100%).")
    severity = models.PositiveSmallIntegerField(validators=LEVEL, help_text="1 (minor) to 5 (severe).")
    impact = models.PositiveSmallIntegerField(validators=LEVEL, help_text="Business impact, 1 to 5.")
    propagation_threshold = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="An edge propagates when its effective probability is at least this value.",
    )
    business_impact = models.TextField(blank=True)
    asset_categories = models.CharField(max_length=255, blank=True, help_text="Comma-separated list.")
    assumptions = models.TextField(blank=True)
    preventive_measures = models.TextField(blank=True)
    detective_measures = models.TextField(blank=True, help_text="Detective and recovery measures.")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="scenarios"
    )
    visibility = models.CharField(max_length=8, choices=Visibility.choices, default=Visibility.PRIVATE)
    status = models.CharField(max_length=8, choices=ScenarioStatus.choices, default=ScenarioStatus.ACTIVE)
    is_system = models.BooleanField(default=False, help_text="Seeded scenario; protected from deletion.")
    version = models.PositiveIntegerField(default=1)
    controls = models.ManyToManyField(SecurityControl, through="ScenarioControl", related_name="scenarios")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["status", "visibility"])]
        constraints = [
            models.CheckConstraint(condition=Q(likelihood__lte=100), name="scenario_likelihood_range"),
            models.CheckConstraint(condition=Q(severity__gte=1, severity__lte=5), name="scenario_severity_range"),
            models.CheckConstraint(condition=Q(impact__gte=1, impact__lte=5), name="scenario_impact_range"),
            models.CheckConstraint(
                condition=Q(propagation_threshold__gte=1, propagation_threshold__lte=100),
                name="scenario_threshold_range",
            ),
            models.CheckConstraint(
                condition=Q(visibility="shared") | Q(owner__isnull=False), name="private_scenario_has_owner"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == ScenarioStatus.ACTIVE

    def asset_list(self):
        return [a.strip() for a in self.asset_categories.split(",") if a.strip()]


class PropagationRule(models.Model):
    """A scenario-specific directed edge: compromise may spread source -> target."""

    scenario = models.ForeignKey(ThreatScenario, on_delete=models.CASCADE, related_name="rules")
    source = models.ForeignKey(SupplyChainStage, on_delete=models.PROTECT, related_name="outgoing_rules")
    target = models.ForeignKey(SupplyChainStage, on_delete=models.PROTECT, related_name="incoming_rules")
    probability = models.PositiveSmallIntegerField(validators=PERCENT, help_text="Propagation probability (0-100%).")
    rationale = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["source__position", "target__position"]
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "source", "target"],
                name="unique_rule_per_edge",
                violation_error_message="Duplicate propagation rule: each source and target pair may appear only once.",
            ),
            models.CheckConstraint(
                condition=~Q(source=F("target")),
                name="rule_not_self_loop",
                violation_error_message="A stage cannot propagate to itself.",
            ),
            models.CheckConstraint(condition=Q(probability__lte=100), name="rule_probability_range"),
        ]

    def __str__(self):
        return f"{self.source} -> {self.target} ({self.probability}%)"

    @property
    def kind(self):
        return edge_kind(self.source.position, self.target.position)


class ScenarioControl(models.Model):
    """Marks a catalog control as relevant to a scenario."""

    scenario = models.ForeignKey(ThreatScenario, on_delete=models.CASCADE, related_name="scenario_controls")
    control = models.ForeignKey(SecurityControl, on_delete=models.PROTECT, related_name="scenario_links")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scenario", "control"], name="unique_scenario_control")]

    def __str__(self):
        return f"{self.scenario} / {self.control}"
