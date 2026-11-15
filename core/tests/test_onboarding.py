"""The Overview's "Get started" checklist (core/onboarding.py)."""

import pytest
from django.urls import reverse

from accounts import two_factor
from accounts.preferences import preferences_for
from core.onboarding import checklist
from remediation import services as remediation
from simulation.tests.test_services_and_views import run_for

pytestmark = pytest.mark.django_db
OVERVIEW = reverse("core:dashboard")


def fresh(user):
    """The user as a request would load it (role and preferences not cached)."""
    return type(user).objects.get(pk=user.pk)


def keys(user):
    user = fresh(user)
    return [(s.key, s.done) for s in checklist(user)["steps"]]


def test_a_new_analyst_sees_every_step_open(seeded, analyst, analyst_client):
    assert keys(analyst) == [("simulate", False), ("controls", False), ("plan", False), ("secure", False)]
    page = analyst_client.get(OVERVIEW).content.decode()
    assert "Get started" in page and "0 of 4 done" in page
    assert 'max="4" value="0"' in page


def test_steps_tick_themselves_off_from_real_data(seeded, analyst):
    run = run_for(analyst)
    assert dict(keys(analyst))["simulate"] and not dict(keys(analyst))["controls"]
    run_for(analyst, controls=["mfa"])
    assert dict(keys(analyst))["controls"]
    remediation.track(analyst, run, run.result["recommendations"][0]["control"])
    assert dict(keys(analyst))["plan"]
    two_factor.enable(analyst, two_factor.new_secret(), 0)
    state = checklist(fresh(analyst))
    assert state["done"] == state["total"] and not state["visible"]


def test_admins_are_asked_to_invite_their_team(seeded, admin_user, analyst):
    steps = dict(keys(admin_user))
    # The conftest admin shares the default workspace with the analyst, so it counts as done.
    assert "invite" in steps and steps["invite"] is True


def test_viewers_get_reading_steps_not_simulation_steps(seeded, viewer):
    assert [k for k, _ in keys(viewer)] == ["read", "secure"]


def test_hiding_and_showing_it_again(seeded, analyst, analyst_client):
    analyst_client.post(reverse("core:onboarding_toggle"))
    assert preferences_for(fresh(analyst)).onboarding_dismissed_at is not None
    page = analyst_client.get(OVERVIEW).content.decode()
    assert "0 of 4 done" not in page and "Show it again" in page
    analyst_client.post(reverse("core:onboarding_toggle"), {"show": "1"})
    assert preferences_for(fresh(analyst)).onboarding_dismissed_at is None
    assert "0 of 4 done" in analyst_client.get(OVERVIEW).content.decode()


def test_toggle_needs_post(seeded, analyst_client):
    assert analyst_client.get(reverse("core:onboarding_toggle")).status_code == 405
