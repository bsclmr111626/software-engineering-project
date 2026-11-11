from types import SimpleNamespace

import pytest

from code_scans.services.simulation_mapping import (
    scenario_slug_for_finding,
)


@pytest.mark.parametrize(
    "finding",
    [
        SimpleNamespace(
            rule_id="py/command-line-injection",
            tags=[],
        ),
        SimpleNamespace(
            rule_id="some/other-rule",
            tags=["security", "external/cwe/cwe-078"],
        ),
        SimpleNamespace(
            rule_id="some/other-rule",
            tags=["external/cwe/cwe-088"],
        ),
    ],
)
def test_command_injection_finding_maps_to_application_scenario(finding):
    assert scenario_slug_for_finding(finding) == ("application-command-injection")


def test_unmapped_finding_returns_none():
    finding = SimpleNamespace(
        rule_id="some/unmapped-rule",
        tags=["security"],
    )

    assert scenario_slug_for_finding(finding) is None


def test_javascript_sql_injection_maps_to_application_scenario():
    finding = SimpleNamespace(
        rule_id="js/sql-injection",
        tags=[
            "security",
            "external/cwe/cwe-089",
            "external/cwe/cwe-090",
            "external/cwe/cwe-943",
        ],
    )

    assert scenario_slug_for_finding(finding) == ("application-sql-injection")


def test_javascript_command_injection_maps_to_application_scenario():
    finding = SimpleNamespace(
        rule_id="js/command-line-injection",
        tags=[
            "security",
            "external/cwe/cwe-078",
            "external/cwe/cwe-088",
        ],
    )

    assert scenario_slug_for_finding(finding) == ("application-command-injection")


def test_javascript_path_injection_maps_to_application_scenario():
    finding = SimpleNamespace(
        rule_id="js/path-injection",
        tags=[
            "security",
            "external/cwe/cwe-022",
            "external/cwe/cwe-023",
            "external/cwe/cwe-036",
        ],
    )

    assert scenario_slug_for_finding(finding) == ("application-path-traversal")


@pytest.mark.parametrize(
    ("cwe", "expected"),
    [
        ("cwe-089", "application-sql-injection"),
        ("cwe-090", "application-sql-injection"),
        ("cwe-943", "application-sql-injection"),
        ("cwe-022", "application-path-traversal"),
        ("cwe-023", "application-path-traversal"),
        ("cwe-036", "application-path-traversal"),
        ("cwe-078", "application-command-injection"),
        ("cwe-088", "application-command-injection"),
    ],
)
def test_cwe_fallback_mapping(cwe, expected):
    finding = SimpleNamespace(
        rule_id="some/other-rule",
        tags=[f"external/cwe/{cwe}"],
    )

    assert scenario_slug_for_finding(finding) == expected


@pytest.mark.parametrize(
    "rule_id",
    [
        "js/missing-rate-limiting",
        "js/code-injection",
    ],
)
def test_unrelated_javascript_findings_remain_unmapped(rule_id):
    finding = SimpleNamespace(
        rule_id=rule_id,
        tags=["security"],
    )

    assert scenario_slug_for_finding(finding) is None
