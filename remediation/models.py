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
    """A recommended control that someone has committed to act on.

    Created from a report's recommendation, so it keeps the run it came from
    and the modeled reduction at that time. Whether the change has been
    verified is derived from later runs (``services.verification``), not
    stored, so it cannot go stale.

    Who can see it (``services.items_for``): the person who added it
    (``owner``), the colleague it is assigned to, and, once ``is_shared`` is
    on, every member of its workspace. Never anyone in another workspace.
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="remediation_items")
    workspace = models.ForeignKey("accounts.Workspace", on_delete=models.PROTECT, related_name="remediation_items")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remediation_assigned",
        help_text="The colleague responsible for doing the work.",
    )
    is_shared = models.BooleanField(
        default=False, help_text="Visible to every member of the workspace, not only the owner and assignee."
    )
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
    evidence_url = models.URLField(
        "Evidence link",
        blank=True,
        max_length=500,
        help_text="A ticket, pull request or document that shows the work, for example a Jira or GitHub link.",
    )
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["workspace", "status"], name="remediation_ws_status_idx"),
            models.Index(fields=["assignee", "status"], name="remediation_assignee_idx"),
        ]
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

    def save(self, *args, **kwargs):
        # An item always lives in the workspace of the person who added it.
        if self.workspace_id is None and self.owner_id is not None:
            from accounts.workspaces import workspace_of

            self.workspace = workspace_of(self.owner)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES


class ActivityKind(models.TextChoices):
    CREATED = "created", "Added to the plan"
    STATUS = "status", "Changed the status"
    ASSIGNEE = "assignee", "Changed who it is assigned to"
    DUE_DATE = "due_date", "Changed the due date"
    EVIDENCE = "evidence", "Changed the evidence link"
    NOTE = "note", "Edited the notes"
    SHARING = "sharing", "Changed who can see it"
    COMMENT = "comment", "Commented"


class RemediationActivity(models.Model):
    """One entry in an item's history: a change or a comment, with who made it.

    ``actor_username`` keeps the name after the account is deleted. Entries are
    never edited; they go when the item goes.
    """

    item = models.ForeignKey(RemediationItem, on_delete=models.CASCADE, related_name="activity")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_username = models.CharField(max_length=150, blank=True)
    kind = models.CharField(max_length=16, choices=ActivityKind.choices)
    old_value = models.CharField(max_length=200, blank=True)
    new_value = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "remediation activity"

    def __str__(self):
        return f"{self.actor_username or 'Someone'}: {self.get_kind_display()}"
