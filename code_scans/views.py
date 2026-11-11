
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Prefetch

from accounts.permissions import analyst_required
from audit.models import AuditAction
from audit.services import record_event
from simulation.models import SimulationRun

from .forms import CodeScanUploadForm
from .models import CodeScan
from .services.scanner import process_code_scan
from .services.simulation_mapping import scenario_slug_for_finding


logger = logging.getLogger(__name__)


@analyst_required
def scan_list(request):
    scans = CodeScan.objects.filter(
        owner=request.user
    ).order_by("-created_at")

    paginator = Paginator(scans, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "code_scans/list.html",
        {
            "page_obj": page_obj,
            "scans": page_obj.object_list,
            "nav_section": "code_scans",
        },
    )


@analyst_required
def scan_upload(request):
    if request.method == "POST":
        form = CodeScanUploadForm(request.POST, request.FILES)

        if form.is_valid():
            archive = form.cleaned_data["archive"]
            project_name = form.cleaned_data["project_name"]

            scan = CodeScan.objects.create(
                owner=request.user,
                project_name=project_name,
                uploaded_filename=archive.name[:255],
                status=CodeScan.Status.PENDING,
            )

            try:
                record_event(
                    request.user,
                    AuditAction.CODE_SCAN_UPLOAD,
                    target=scan,
                    request=request,
                    project_name=project_name,
                    filename=archive.name,
                )

                process_code_scan(scan, archive)

                record_event(
                    request.user,
                    AuditAction.CODE_SCAN_COMPLETE,
                    target=scan,
                    request=request,
                    total_findings=scan.total_findings,
                    critical_findings=scan.critical_findings,
                    high_findings=scan.high_findings,
                    medium_findings=scan.medium_findings,
                    low_findings=scan.low_findings,
                )

                messages.success(
                    request,
                    "Source code scan completed successfully.",
                )

            except Exception:
                logger.exception(
                    "Code scan failed. Scan ID: %s",
                    scan.pk,
                )

                try:
                    record_event(
                        request.user,
                        AuditAction.CODE_SCAN_FAILED,
                        target=scan,
                        request=request,
                        project_name=scan.project_name,
                    )
                except Exception:
                    logger.exception(
                        "Could not record failed scan audit event: %s",
                        scan.pk,
                    )

                messages.error(
                    request,
                    "The scan could not be completed. "
                    "Check the scan details or contact an administrator.",
                )

            return redirect(
                "code_scans:detail",
                scan_id=scan.pk,
            )

    else:
        form = CodeScanUploadForm()

    return render(
        request,
        "code_scans/upload.html",
        {
            "form": form,
            "nav_section": "code_scans",
        },
    )


@analyst_required
def scan_detail(request, scan_id):
    scan = get_object_or_404(
        CodeScan.objects.prefetch_related("findings"),
        pk=scan_id,
        owner=request.user,
    )

    findings = scan.findings.all().prefetch_related(
        Prefetch(
            "simulation_runs",
            queryset=SimulationRun.objects.filter(
                user=request.user
            ).order_by("-created_at"),
            to_attr="visible_simulation_runs",
        )
    )

    severity = request.GET.get("severity", "").lower()

    valid_severities = {
        choice[0]
        for choice in scan.findings.model.Severity.choices
    }

    if severity in valid_severities:
        findings = findings.filter(severity=severity)
    else:
        severity = ""

    paginator = Paginator(findings, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    simulation_scenarios = {
        finding.pk: scenario_slug
        for finding in page_obj.object_list
        if (scenario_slug := scenario_slug_for_finding(finding))
    }

    return render(
        request,
        "code_scans/detail.html",
        {
            "scan": scan,
            "page_obj": page_obj,
            "findings": page_obj.object_list,
            "selected_severity": severity,
            "severity_choices": scan.findings.model.Severity.choices,
            "simulation_scenarios": simulation_scenarios,
            "nav_section": "code_scans",
        },
    )
