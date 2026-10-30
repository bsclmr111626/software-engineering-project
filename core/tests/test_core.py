import base64
import hashlib

import pytest
from django.test import override_settings
from django.urls import reverse

from core.templatetags.codeguard_tags import initials
from core.theme import INIT_SCRIPT
from simulation.models import SimulationRun
from simulation.services import run_simulation
from simulation.visual import build_pipeline
from threats.models import ThreatScenario

pytestmark = pytest.mark.django_db


def test_landing_page_is_public(seeded, client):
    response = client.get(reverse("core:landing"))
    assert response.status_code == 200
    assert b"CodeGuard" in response.content
    assert b"Create an account" in response.content


def test_methodology_page_is_public_and_shows_formulas(seeded, client):
    response = client.get(reverse("core:help"))
    assert response.status_code == 200
    assert b"Residual risk" in response.content
    assert b"not a replacement for a professional security assessment" in response.content


def test_dashboard_empty_state(seeded, analyst_client):
    response = analyst_client.get(reverse("core:dashboard"))
    assert response.status_code == 200
    metrics = response.context["metrics"]
    assert metrics["run_total"] == 0
    assert metrics["average_residual"] is None
    assert metrics["scenario_count"] == 6
    assert b"No simulation history yet" in response.content


def test_dashboard_metrics_reflect_database(seeded, analyst, analyst_client):
    for slug in ("compromised-cicd-pipeline", "production-credential-exposure"):
        scenario = ThreatScenario.objects.get(slug=slug)
        run_simulation(
            analyst, scenario, likelihood=scenario.likelihood, severity=scenario.severity,
            impact=scenario.impact, threshold=scenario.propagation_threshold, controls=[],
        )  # fmt: skip
    runs = SimulationRun.objects.all()
    response = analyst_client.get(reverse("core:dashboard"))
    metrics = response.context["metrics"]
    assert metrics["run_total"] == 2
    expected_avg = round(sum(r.residual_risk for r in runs) / 2, 1)
    assert metrics["average_residual"] == expected_avg
    assert metrics["high_risk"] == sum(1 for r in runs if r.classification in ("high", "critical"))
    assert dict(metrics["band_counts"])["high"] == 1  # CI/CD scenario scores 37.7
    production = next(row for row in metrics["stage_rows"] if row["stage_key"] == "production")
    assert production["compromised"] == 2
    chart = analyst_client.get(reverse("core:dashboard_chart"))
    assert chart["Content-Type"] == "image/png"


def test_dashboard_excludes_other_users_private_runs(seeded, analyst, other_analyst, analyst_client):
    scenario = ThreatScenario.objects.first()
    run_simulation(other_analyst, scenario, likelihood=50, severity=3, impact=3, threshold=50, controls=[])
    assert analyst_client.get(reverse("core:dashboard")).context["metrics"]["run_total"] == 0


def test_security_headers_present(seeded, client):
    response = client.get(reverse("core:landing"))
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert "'unsafe-inline'" not in response["Content-Security-Policy"]
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


def test_theme_script_runs_first_and_is_the_only_inline_script_the_csp_allows(seeded, analyst_client):
    response = analyst_client.get(reverse("core:dashboard"))
    html = response.content.decode()
    script = f"<script>{INIT_SCRIPT}</script>"
    assert html.index(script) < html.index('rel="stylesheet"')
    assert html.count("<script>") == 1
    digest = base64.b64encode(hashlib.sha256(INIT_SCRIPT.encode()).digest()).decode()
    assert f"script-src 'self' 'sha256-{digest}';" in response["Content-Security-Policy"]
    assert "data-theme-toggle hidden" in html  # revealed by app.js, so it never shows without JavaScript


@pytest.mark.parametrize(
    "username, expected", [("demo_admin", "DA"), ("alice", "A"), ("j.doe-smith", "JD"), ("__", "?")]
)
def test_initials(username, expected):
    assert initials(username) == expected


def test_account_menu(seeded, analyst_client):
    html = analyst_client.get(reverse("core:dashboard")).content.decode()
    menu = html[html.index('<div class="dropdown">') : html.index("</header>")]
    assert '<span class="cg-avatar" aria-hidden="true">A</span>' in menu
    assert 'aria-label="Account menu for alice"' in menu
    for name in ("settings:profile", "settings:index", "settings:appearance", "settings:security"):
        assert f'href="{reverse(name)}"' in menu
    assert reverse("settings:users") not in menu  # administrators only
    # Sign out stays a CSRF-protected POST.
    assert f'<form method="post" action="{reverse("accounts:logout")}" class="cg-menu-form">' in menu
    assert "csrfmiddlewaretoken" in menu


def test_account_menu_offers_user_management_to_admins(seeded, admin_client):
    html = admin_client.get(reverse("core:dashboard")).content.decode()
    assert f'href="{reverse("settings:users")}"' in html


def test_preferences_are_rendered_on_the_html_element(seeded, analyst, analyst_client):
    from accounts.preferences import preferences_for

    preferences = preferences_for(analyst)
    preferences.color_mode = "dark"
    preferences.accent = "iris"
    preferences.text_size = "large"
    preferences.increase_contrast = True
    preferences.save()
    html = analyst_client.get(reverse("core:dashboard")).content.decode()
    tag = html[html.index("<html") : html.index(">", html.index("<html"))]
    for attribute in ('data-theme-pref="dark"', 'data-accent="iris"', 'data-text-size="large"', 'data-contrast="more"'):
        assert attribute in tag


def test_visitors_get_no_preference_attributes(seeded, client):
    html = client.get(reverse("core:landing")).content.decode()
    assert '<html lang="en">' in html


def test_run_status_is_a_dot_and_text(seeded, analyst, analyst_client):
    scenario = ThreatScenario.objects.first()
    run_simulation(analyst, scenario, likelihood=50, severity=3, impact=3, threshold=50, controls=[])
    html = analyst_client.get(reverse("core:dashboard")).content.decode()
    assert (
        '<span class="cg-status cg-status-completed"><span class="cg-status-dot" aria-hidden="true"></span>Completed</span>'
        in html
    )
    assert '<span class="tag">Completed</span>' not in html


def test_custom_404_page_has_no_debug_details(analyst_client):
    response = analyst_client.get("/does-not-exist/")
    assert response.status_code == 404
    assert b"Page not found" in response.content
    assert b"Traceback" not in response.content


def test_custom_403_page(seeded, viewer_client):
    response = viewer_client.get(reverse("threats:create"))
    assert response.status_code == 403
    assert b"You do not have permission" in response.content


def test_csrf_failure_page(analyst):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(analyst)
    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 403
    assert b"CSRF" in response.content


@override_settings(DEBUG=False)
def test_server_error_page_hides_details(rf):
    from core.views import server_error

    response = server_error(rf.get("/"))
    assert response.status_code == 500
    assert b"No details are shown" in response.content


def test_pipeline_geometry():
    stages = [{"key": k, "name": k.title(), "position": i} for i, k in enumerate(["a", "b", "c"], start=1)]
    edges = [
        {"source": "a", "target": "b", "status": "propagated", "label": "80%"},
        {"source": "a", "target": "c", "status": "blocked_by_controls", "label": "40%"},
        {"source": "c", "target": "a", "status": "below_threshold", "label": "20%"},
        {"source": "a", "target": "zzz", "status": "rule", "label": "ignored"},
    ]
    pipeline = build_pipeline(stages, edges)
    assert [n["key"] for n in pipeline["nodes"]] == ["a", "b", "c"]
    assert [e["kind"] for e in pipeline["edges"]] == ["forward", "bypass", "reverse"]
    assert pipeline["edges"][0]["path"].startswith("M ")
    assert pipeline["nodes"][0]["risk"] is None


def test_health_check_is_public_and_minimal(client):
    response = client.get(reverse("core:healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert "no-cache" in response["Cache-Control"]
    assert client.post(reverse("core:healthz")).status_code == 405


def test_health_check_reports_database_failure(client):
    from unittest import mock

    with mock.patch("core.views.connection.cursor", side_effect=RuntimeError("db down")):
        response = client.get(reverse("core:healthz"))
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert "db down" not in response.content.decode()


def test_request_id_is_generated_or_propagated(client):
    generated = client.get(reverse("core:landing"))["X-Request-ID"]
    assert len(generated) == 32
    assert client.get(reverse("core:landing"), HTTP_X_REQUEST_ID="lb-abc.123")["X-Request-ID"] == "lb-abc.123"
    # Malformed or oversized IDs (log injection) are replaced, not echoed.
    bad = client.get(reverse("core:landing"), HTTP_X_REQUEST_ID="evil\nheader")["X-Request-ID"]
    assert bad != "evil\nheader" and len(bad) == 32


def test_json_log_lines_carry_the_request_id():
    import json
    import logging

    from core.observability import JsonFormatter, RequestIdFilter, _request_id

    record = logging.LogRecord("codeguard", logging.INFO, __file__, 1, "run %s done", ("abc",), None)
    token = _request_id.set("req-1")
    try:
        RequestIdFilter().filter(record)
    finally:
        _request_id.reset(token)
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "run abc done" and line["request_id"] == "req-1" and line["level"] == "INFO"


def test_sqlite_runs_in_wal_mode_with_immediate_transactions(tmp_path, settings):
    """A file database (not the in-memory test DB) gets the production pragmas."""
    from django.db.backends.sqlite3.base import DatabaseWrapper

    config = {**settings.DATABASES["default"], "NAME": str(tmp_path / "probe.sqlite3")}
    wrapper = DatabaseWrapper(config, alias="probe")
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0] == "wal"
            cursor.execute("PRAGMA synchronous")
            assert cursor.fetchone()[0] == 1  # NORMAL
        assert wrapper.transaction_mode == "IMMEDIATE"
    finally:
        wrapper.close()


def test_backup_db_writes_a_verified_copy_and_rotates(tmp_path):
    import sqlite3
    from unittest import mock

    from django.core.management import call_command
    from django.db import connection

    source = tmp_path / "live.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE t (x INTEGER)")
        db.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(100)])
    out = tmp_path / "backups"
    with mock.patch.dict(connection.settings_dict, {"NAME": str(source)}):
        for _ in range(3):
            call_command("backup_db", "--output", str(out), "--keep", "2")
    copies = sorted(out.glob("codeguard-*.sqlite3"))
    assert len(copies) == 2
    with sqlite3.connect(copies[-1]) as db:
        assert db.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 100
