"""Tests for the CI helper scripts used by the Jenkinsfile."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load("ci_dependency_audit")


def test_clean_report_passes():
    report = json.dumps({"dependencies": [{"name": "django", "version": "5.2.18", "vulns": []}]})
    assert audit.classify(report) == (audit.NO_VULNERABILITIES, [])


def test_vulnerable_report_fails_regardless_of_formatting():
    data = {"dependencies": [{"name": "examplepkg", "version": "1.0", "vulns": [{"id": "PYSEC-0000-0"}]}]}
    for text in (json.dumps(data), json.dumps(data, indent=2), json.dumps(data, separators=(",", ":"))):
        assert audit.classify(text) == (audit.VULNERABLE, ["examplepkg"])


def test_missing_or_garbled_report_is_incomplete():
    assert audit.classify("")[0] == audit.INCOMPLETE
    assert audit.classify("not json")[0] == audit.INCOMPLETE
    assert audit.classify(json.dumps({"unexpected": True}))[0] == audit.INCOMPLETE


def test_jenkinsfile_uses_scripts_and_no_sandbox_restricted_calls():
    text = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    assert "scripts/ci_deploy_check.py" in text
    assert "scripts/ci_dependency_audit.py" in text
    assert "UUID." not in text  # would need Groovy script approval
    for stage in ("Checkout", "Environment setup", "Static checks", "Database preparation",
                  "Automated tests", "Coverage gate", "Security checks"):  # fmt: skip
        assert f"stage('{stage}')" in text
