
import pytest
from django.urls import reverse

from code_scans.models import CodeFinding, CodeScan
from simulation import services
from simulation.models import RunStatus
from threats.models import ThreatScenario


pytestmark = pytest.mark.django_db


def create_finding(user):
    scan = CodeScan.objects.create(
        owner=user,
        project_name="Simulation history test",
        uploaded_filename="source.zip",
        languages=["python"],
        status=CodeScan.Status.COMPLETED,
    )

    return CodeFinding.objects.create(
        scan=scan,
        rule_id="py/command-line-injection",
        rule_name="Command-line injection",
        message="User-controlled input reaches a command execution function.",
        severity=CodeFinding.Severity.CRITICAL,
        file_path="app.py",
        start_line=9,
        tags=[
            "security",
            "external/cwe/cwe-078",
            "external/cwe/cwe-088",
        ],
    )


def create_linked_simulation(user, finding):
    scenario = ThreatScenario.objects.get(
        slug="application-command-injection"
    )

    return services.run_simulation(
        user,
        scenario,
        likelihood=scenario.likelihood,
        severity=scenario.severity,
        impact=scenario.impact,
        threshold=scenario.propagation_threshold,
        controls=list(scenario.controls.all()),
        code_finding=finding,
    )


class TestCodeFindingSimulationHistory:
    def test_finding_owner_sees_linked_simulation_history(
        self, seeded, analyst, analyst_client
    ):
        finding = create_finding(analyst)
        run = create_linked_simulation(analyst, finding)

        response = analyst_client.get(
            reverse("code_scans:detail", args=[finding.scan_id])
        )

        assert response.status_code == 200
        assert run.status == RunStatus.COMPLETED

        assert str(run.id) in response.content.decode()
        assert reverse(
            "simulation:detail", args=[run.id]
        ) in response.content.decode()
        assert "Threat simulation history" in response.content.decode()

    def test_another_user_cannot_access_finding_or_its_simulation_history(
        self, seeded, analyst, client, other_analyst
    ):
        finding = create_finding(analyst)
        run = create_linked_simulation(analyst, finding)

        client.force_login(other_analyst)

        response = client.get(
            reverse("code_scans:detail", args=[finding.scan_id])
        )

        assert response.status_code == 404
        assert str(run.id) not in response.content.decode()

    def test_finding_without_simulations_has_no_history_section(
        self, seeded, analyst, analyst_client
    ):
        finding = create_finding(analyst)

        response = analyst_client.get(
            reverse("code_scans:detail", args=[finding.scan_id])
        )

        assert response.status_code == 200
        assert "Threat simulation history" not in response.content.decode()
