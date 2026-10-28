"""The settings center: every preference persists and changes behaviour."""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.preferences import preferences_for
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD
from simulation.models import SimulationRun
from simulation.services import run_simulation
from threats.models import ThreatScenario

pytestmark = pytest.mark.django_db


def _run(user, slug="compromised-developer-account"):
    scenario = ThreatScenario.objects.get(slug=slug)
    return run_simulation(user, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])


@pytest.mark.parametrize(
    "name", ["profile", "account", "appearance", "typography", "display", "accessibility", "notifications",
             "privacy", "security", "sessions"],
)  # fmt: skip
def test_every_settings_page_renders_with_its_navigation(analyst_client, name):
    html = analyst_client.get(reverse(f"settings:{name}")).content.decode()
    assert '<nav class="cg-settings-nav" aria-label="Settings">' in html
    assert f'href="{reverse(f"settings:{name}")}" aria-current="page"' in html
    assert reverse("settings:users") not in html  # administration is hidden from non-admins


def test_settings_require_login(client):
    response = client.get(reverse("settings:appearance"))
    assert response.status_code == 302 and reverse("accounts:login") in response.url


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def test_administration_pages_are_admin_only(analyst, viewer, admin_user):
    for name in ("users", "organization"):
        assert _client(analyst).get(reverse(f"settings:{name}")).status_code == 403
        assert _client(viewer).get(reverse(f"settings:{name}")).status_code == 403
        assert _client(admin_user).get(reverse(f"settings:{name}")).status_code == 200


def test_profile_saves_name_and_details(analyst_client, analyst):
    response = analyst_client.post(
        reverse("settings:profile"),
        {"first_name": "Alice", "last_name": "Ng", "job_title": "AppSec engineer", "team": "Platform"},
    )
    assert response.status_code == 302
    analyst.refresh_from_db()
    assert (analyst.first_name, analyst.last_name) == ("Alice", "Ng")
    assert (analyst.profile.job_title, analyst.profile.team) == ("AppSec engineer", "Platform")
    assert AuditEvent.objects.filter(action=AuditAction.PROFILE_UPDATE, actor=analyst).exists()
    assert (
        '<span class="cg-avatar" aria-hidden="true">AN</span>'
        in analyst_client.get(reverse("core:dashboard")).content.decode()
    )


def test_email_change_requires_the_current_password(analyst_client, analyst):
    url = reverse("settings:account")
    wrong = analyst_client.post(url, {"email": "new@example.com", "current_password": "nope"})
    assert wrong.status_code == 200 and "The password is incorrect." in wrong.content.decode()
    analyst.refresh_from_db()
    assert analyst.email == "alice@example.com"
    assert analyst_client.post(url, {"email": "New@Example.com", "current_password": PASSWORD}).status_code == 302
    analyst.refresh_from_db()
    assert analyst.email == "new@example.com"
    assert AuditEvent.objects.filter(action=AuditAction.EMAIL_CHANGE, actor=analyst).exists()


def test_email_change_rejects_an_address_in_use(analyst_client, other_analyst):
    response = analyst_client.post(
        reverse("settings:account"), {"email": "BOB@example.com", "current_password": PASSWORD}
    )
    assert "already exists" in response.content.decode()


def test_appearance_is_saved_and_rendered(analyst_client, analyst):
    analyst_client.post(
        reverse("settings:appearance"), {"color_mode": "dark", "surface": "pearl", "accent": "graphite"}
    )
    preferences = preferences_for(get_user_model().objects.get(pk=analyst.pk))
    assert (preferences.color_mode, preferences.surface, preferences.accent) == ("dark", "pearl", "graphite")
    html = analyst_client.get(reverse("threats:list")).content.decode()
    assert 'data-theme-pref="dark"' in html and 'data-accent="graphite"' in html and 'data-surface="pearl"' in html


def test_invalid_preference_values_are_rejected(analyst_client, analyst):
    response = analyst_client.post(
        reverse("settings:appearance"), {"color_mode": "neon", "surface": "paper", "accent": "ultramarine"}
    )
    assert response.status_code == 200
    assert preferences_for(analyst).color_mode == "system"


def test_a_page_saves_only_its_own_fields(analyst_client, analyst):
    analyst_client.post(reverse("settings:appearance"), {"color_mode": "dark", "surface": "paper", "accent": "iris"})
    analyst_client.post(reverse("settings:typography"), {"text_size": "larger", "heading_font": "sans"})
    preferences = preferences_for(get_user_model().objects.get(pk=analyst.pk))
    assert (preferences.color_mode, preferences.text_size, preferences.heading_font) == ("dark", "larger", "sans")


def test_quick_theme_toggle_saves_the_color_mode(analyst_client, analyst):
    response = analyst_client.post(reverse("settings:quick_theme"), {"mode": "dark"}, HTTP_X_REQUESTED_WITH="fetch")
    assert response.status_code == 204
    assert preferences_for(get_user_model().objects.get(pk=analyst.pk)).color_mode == "dark"
    response = analyst_client.post(reverse("settings:quick_theme"), {"mode": "light", "next": "https://evil.example/"})
    assert response.url == reverse("core:dashboard")  # no open redirect
    assert analyst_client.get(reverse("settings:quick_theme")).status_code == 405


def test_page_size_preference_is_used_by_lists(seeded, analyst_client, analyst):
    analyst_client.post(
        reverse("settings:display"),
        {"density": "compact", "timestamp_style": "absolute", "page_size": 10, "start_page": "reports"},
    )
    for _ in range(11):
        _run(analyst)
    page = analyst_client.get(reverse("reports:list")).context["page_obj"]
    assert page.paginator.per_page == 10 and page.paginator.num_pages == 2
    html = analyst_client.get(reverse("reports:list")).content.decode()
    assert 'data-density="compact"' in html


def test_start_page_preference_is_where_sign_in_lands(seeded, client, analyst):
    preferences = preferences_for(analyst)
    preferences.start_page = "supply_chain"
    preferences.save()
    response = client.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD}, follow=True)
    assert response.redirect_chain[-1][0] == reverse("core:supply_chain")


def test_absolute_timestamps_preference(seeded, analyst_client, analyst):
    run = _run(analyst)
    preferences = preferences_for(analyst)
    preferences.timestamp_style = "absolute"
    preferences.save()
    html = analyst_client.get(reverse("reports:list")).content.decode()
    assert f'title="{run.created_at:%Y-%m-%d %H:%M}">{run.created_at:%Y-%m-%d %H:%M}</time>' in html


def test_accessibility_switches_are_rendered(analyst_client, analyst):
    analyst_client.post(
        reverse("settings:accessibility"), {"reduce_motion": "on", "increase_contrast": "on", "underline_links": "on"}
    )
    html = analyst_client.get(reverse("core:dashboard")).content.decode()
    for attribute in ('data-motion="reduce"', 'data-contrast="more"', 'data-links="underline"'):
        assert attribute in html


def test_share_by_default_shares_new_reports(seeded, analyst_client, analyst):
    analyst_client.post(reverse("settings:privacy"), {"share_reports_by_default": "on"})
    analyst_client.post(
        reverse("simulation:configure"),
        {"scenario": "compromised-developer-account", "likelihood": 70, "severity": 4, "impact": 4, "threshold": 50},
    )
    run = SimulationRun.objects.get(user=analyst)
    assert run.is_shared
    assert AuditEvent.objects.filter(action=AuditAction.REPORT_SHARE, object_id=str(run.pk)).exists()


def test_data_export_contains_only_own_data_and_is_audited(seeded, analyst_client, analyst, other_analyst):
    mine, theirs = _run(analyst), _run(other_analyst)
    response = analyst_client.get(reverse("settings:export_data"))
    assert response["Content-Type"] == "application/json"
    assert "attachment" in response["Content-Disposition"]
    data = json.loads(response.content)
    assert data["account"]["username"] == "alice"
    assert [r["id"] for r in data["simulation_runs"]] == [str(mine.id)]
    assert str(theirs.id) not in response.content.decode()
    assert "password" not in json.dumps(data["account"]).lower()
    assert AuditEvent.objects.filter(action=AuditAction.DATA_EXPORT, actor=analyst).exists()


def test_signing_out_other_sessions(analyst):
    first, second = Client(), Client()
    for c in (first, second):
        assert c.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD}).status_code == 302
    assert first.post(reverse("settings:revoke_sessions")).status_code == 302
    assert first.get(reverse("core:dashboard")).status_code == 200  # this session survives
    response = second.get(reverse("core:dashboard"))
    assert response.status_code == 302 and response.url == reverse("accounts:login")
    assert second.get(reverse("core:dashboard")).status_code == 302  # and stays signed out
    assert AuditEvent.objects.filter(action=AuditAction.SESSIONS_REVOKED, actor=analyst).count() == 1


def test_sessions_page_describes_this_session(client, analyst):
    client.post(
        reverse("accounts:login"),
        {"username": "alice", "password": PASSWORD},
        HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/130.0 Safari/537.36",
    )
    html = client.get(reverse("settings:sessions")).content.decode()
    assert "Chrome on Windows" in html
    assert "Sign out of all other sessions" in html


def test_users_page_lists_users_and_role_change_redirects_back(admin_client, analyst):
    assert b"alice" in admin_client.get(reverse("settings:users")).content
    response = admin_client.post(reverse("settings:change_role", args=[analyst.pk]), {"role": "viewer"})
    assert response.url == reverse("settings:users")
    analyst.profile.refresh_from_db()
    assert analyst.profile.role == "viewer"
    assert admin_client.get(reverse("accounts:user_list")).url == reverse("settings:users")


def test_surface_defaults_to_paper_and_rejects_unknown_values(analyst_client, analyst):
    assert preferences_for(analyst).surface == "paper"
    assert 'data-surface="paper"' in analyst_client.get(reverse("core:dashboard")).content.decode()
    response = analyst_client.post(
        reverse("settings:appearance"), {"color_mode": "light", "surface": "chrome", "accent": "ultramarine"}
    )
    assert response.status_code == 200
    assert preferences_for(get_user_model().objects.get(pk=analyst.pk)).surface == "paper"


@pytest.mark.parametrize("surface", ["pearl", "sage"])
def test_each_surface_is_saved_and_rendered(analyst_client, analyst, surface):
    analyst_client.post(
        reverse("settings:appearance"), {"color_mode": "light", "surface": surface, "accent": "ultramarine"}
    )
    assert preferences_for(get_user_model().objects.get(pk=analyst.pk)).surface == surface
    assert f'data-surface="{surface}"' in analyst_client.get(reverse("core:dashboard")).content.decode()


def test_retired_neutral_surface_is_rejected(analyst_client, analyst):
    response = analyst_client.post(
        reverse("settings:appearance"), {"color_mode": "light", "surface": "neutral", "accent": "ultramarine"}
    )
    assert response.status_code == 200  # form re-rendered with an error, nothing saved
    assert preferences_for(get_user_model().objects.get(pk=analyst.pk)).surface == "paper"
