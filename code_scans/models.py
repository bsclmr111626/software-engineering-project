
import uuid

from django.conf import settings
from django.db import models


class CodeScan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Language(models.TextChoices):
        PYTHON = "python", "Python"
        JAVASCRIPT = "javascript", "JavaScript / TypeScript"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="code_scans",
    )

    project_name = models.CharField(max_length=150)
    uploaded_filename = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    languages = models.JSONField(default=list, blank=True)

    scanner_version = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)

    total_findings = models.PositiveIntegerField(default=0)
    critical_findings = models.PositiveIntegerField(default=0)
    high_findings = models.PositiveIntegerField(default=0)
    medium_findings = models.PositiveIntegerField(default=0)
    low_findings = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project_name} ({self.status})"


class CodeFinding(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        NOTE = "note", "Note"
        WARNING = "warning", "Warning"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    scan = models.ForeignKey(
        CodeScan,
        on_delete=models.CASCADE,
        related_name="findings",
    )

    rule_id = models.CharField(max_length=255, db_index=True)
    rule_name = models.CharField(max_length=255, blank=True)
    message = models.TextField()

    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.WARNING,
        db_index=True,
    )

    file_path = models.CharField(max_length=1000, blank=True)
    start_line = models.PositiveIntegerField(null=True, blank=True)
    end_line = models.PositiveIntegerField(null=True, blank=True)
    start_column = models.PositiveIntegerField(null=True, blank=True)
    end_column = models.PositiveIntegerField(null=True, blank=True)

    help_uri = models.URLField(max_length=1000, blank=True)
    fingerprint = models.CharField(max_length=255, blank=True)

    tags = models.JSONField(default=list, blank=True)
    properties = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-severity", "file_path", "start_line"]
        indexes = [
            models.Index(fields=["scan", "severity"]),
            models.Index(fields=["scan", "file_path"]),
        ]

    def __str__(self):
        location = self.file_path or "Unknown file"
        if self.start_line:
            location += f":{self.start_line}"
        return f"{self.rule_id} — {location}"
