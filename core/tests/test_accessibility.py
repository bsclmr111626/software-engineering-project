"""Server-side accessibility regression tests.

The full audit (axe-core in a real browser, keyboard focus, reflow) is
documented in docs/test-plan.md; these tests pin the markup that audit
depends on so it cannot silently regress.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from simulation.services import run_simulation
from threats.models import SupplyChainStage, ThreatScenario

pytestmark = pytest.mark.django_db


def describedby_targets_exist(html):
    """Every id referenced by aria-describedby / aria-labelledby must exist in the page."""
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    missing = []
    for attr in re.findall(r'aria-(?:describedby|labelledby)="([^"]+)"', html):
        missing += [ref for ref in attr.split() if ref not in ids]
    return missing


def test_registration_errors_are_announced_and_linked(client):
    response = client.post(
        reverse("accounts:register"),
        {"username": "x", "email": "bad", "password1": "short", "password2": "different"},
    )
    html = response.content.decode()
    assert 'aria-invalid="true"' in html
    assert 'id="id_email_error"' in html
    assert describedby_targets_exist(html) == []


def test_login_error_is_linked_to_inputs(client, analyst):
    html = client.post(reverse("accounts:login"), {"username": "alice", "password": "wrong"}).content.decode()
    assert 'id="login-error"' in html
    assert html.count('aria-describedby="login-error"') == 2
    assert html.count('aria-invalid="true"') == 2


def test_password_reset_form_links_help_and_errors(client):
    html = client.post(reverse("accounts:password_reset"), {"email": "not-an-email"}).content.decode()
    assert 'aria-invalid="true"' in html
    assert describedby_targets_exist(html) == []


def test_scenario_rule_errors_are_linked(seeded, analyst_client):
    stage = SupplyChainStage.objects.get(key="vcs")
    data = {
        "name": "A11y check", "description": "d", "initial_stage": stage.pk, "likelihood": 50, "severity": 3,
        "impact": 3, "propagation_threshold": 50, "rules-TOTAL_FORMS": "1", "rules-INITIAL_FORMS": "0",
        "rules-MIN_NUM_FORMS": "0", "rules-MAX_NUM_FORMS": "20", "rules-0-source": stage.pk,
        "rules-0-target": SupplyChainStage.objects.get(key="cicd").pk, "rules-0-probability": 150,
    }  # fmt: skip
    html = analyst_client.post(reverse("threats:create"), data).content.decode()
    assert 'id="id_rules-0-probability_error"' in html
    assert describedby_targets_exist(html) == []
    assert "<legend" in html  # each rule row is a named group


def test_report_page_names_diagram_tables_and_charts(seeded, analyst, analyst_client):
    scenario = ThreatScenario.objects.get(slug="compromised-developer-account")
    run = run_simulation(analyst, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])
    summary = analyst_client.get(reverse("simulation:detail", args=[run.id])).content.decode()
    assert 'role="img" aria-labelledby="run-graph-title" aria-describedby="run-graph-desc"' in summary
    paths = analyst_client.get(reverse("simulation:detail_section", args=[run.id, "paths"])).content.decode()
    assert re.search(r'<table class="table" aria-label="Every propagation edge', paths)
    alts = []
    for section in ("summary", "stages", "paths", "controls", "method"):
        html = analyst_client.get(reverse("simulation:detail_section", args=[run.id, section])).content.decode()
        alts += re.findall(r'<img class="cg-chart"[^>]*alt="([^"]*)"', html)
        assert describedby_targets_exist(html) == [], section
        assert "<caption" not in html  # hidden captions take up layout in Chrome; tables use aria-label
        assert html.count("<h1") == 1, section
    assert len(alts) == 3
    for alt in alts:
        assert len(alt) > 60  # charts carry a real text alternative with the numbers


def test_active_navigation_is_marked(seeded, analyst_client):
    html = analyst_client.get(reverse("threats:list")).content.decode()
    assert re.search(r'href="/threats/" aria-current="page"', html)
    assert '<nav class="cg-nav" aria-label="Main">' in html
    assert html.count('aria-current="page"') >= 2  # the nav item and the breadcrumb


def test_no_auto_submitting_controls_and_primary_button_uses_accent_tokens():
    templates = Path(settings.BASE_DIR, "templates")
    assert not [p for p in templates.rglob("*.html") if "data-autosubmit" in p.read_text(encoding="utf-8")]
    css = Path(settings.BASE_DIR, "static", "css", "codeguard.css").read_text(encoding="utf-8")
    assert "--bs-btn-color: var(--on-accent); --bs-btn-bg: var(--accent)" in css
    assert "--bs-btn-hover-bg: var(--accent-hover)" in css
