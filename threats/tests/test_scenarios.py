import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from threats.models import (
    PropagationRule,
    ScenarioStatus,
    SecurityControl,
    SupplyChainStage,
    ThreatScenario,
    Visibility,
)
from threats.services import clone_scenario

pytestmark = pytest.mark.django_db


def stage(key):
    return SupplyChainStage.objects.get(key=key)


def scenario_payload(rules=(("vcs", "cicd", 70),), existing=0, **overrides):
    data = {
        "name": "Leaked deploy token",
        "description": "A hypothetical leaked token.",
        "initial_stage": stage("vcs").pk,
        "likelihood": 60,
        "severity": 4,
        "impact": 3,
        "propagation_threshold": 50,
        "business_impact": "Unauthorized releases",
        "asset_categories": "Tokens, Pipelines",
        "assumptions": "Token has write scope",
        "preventive_measures": "",
        "detective_measures": "",
        "controls": [SecurityControl.objects.get(slug="mfa").pk],
        "rules-TOTAL_FORMS": str(len(rules)),
        "rules-INITIAL_FORMS": str(existing),
        "rules-MIN_NUM_FORMS": "0",
        "rules-MAX_NUM_FORMS": "20",
    }
    for i, (source, target, probability) in enumerate(rules):
        data[f"rules-{i}-source"] = stage(source).pk
        data[f"rules-{i}-target"] = stage(target).pk
        data[f"rules-{i}-probability"] = probability
        data[f"rules-{i}-rationale"] = "test"
    data.update(overrides)
    return data


class TestSeedCommand:
    def test_seed_creates_reference_data(self, seeded):
        assert SupplyChainStage.objects.count() == 5
        assert list(SupplyChainStage.objects.values_list("key", flat=True)) == [
            "ide", "vcs", "cicd", "registry", "production",
        ]  # fmt: skip
        assert SecurityControl.objects.count() >= 14
        assert ThreatScenario.objects.filter(is_system=True, visibility=Visibility.SHARED).count() == 6
        for scenario in ThreatScenario.objects.all():
            assert scenario.rules.exists()
            assert scenario.controls.exists()

    def test_seed_is_idempotent(self, seeded):
        counts = (ThreatScenario.objects.count(), PropagationRule.objects.count(), SecurityControl.objects.count())
        call_command("seed_codeguard", verbosity=0)
        call_command("seed_codeguard", verbosity=0)
        assert (
            ThreatScenario.objects.count(),
            PropagationRule.objects.count(),
            SecurityControl.objects.count(),
        ) == counts

    def test_seed_does_not_overwrite_admin_edits_unless_reset(self, seeded):
        scenario = ThreatScenario.objects.get(slug="compromised-cicd-pipeline")
        scenario.likelihood = 11
        scenario.save()
        call_command("seed_codeguard", verbosity=0)
        scenario.refresh_from_db()
        assert scenario.likelihood == 11
        call_command("seed_codeguard", "--reset-scenarios", verbosity=0)
        scenario.refresh_from_db()
        assert scenario.likelihood == 55
        assert scenario.rules.count() == 4

    def test_demo_users_refused_outside_debug(self, seeded):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("seed_codeguard", "--demo-users", verbosity=0)

    def test_demo_users_created_in_debug_with_correct_roles(self, seeded, settings):
        from accounts.permissions import get_role

        settings.DEBUG = True
        call_command("seed_codeguard", "--demo-users", verbosity=0)
        call_command("seed_codeguard", "--demo-users", verbosity=0)  # idempotent
        from django.contrib.auth import get_user_model

        users = {u.username: get_role(u) for u in get_user_model().objects.filter(username__startswith="demo_")}
        assert users == {"demo_admin": "admin", "demo_analyst": "analyst", "demo_viewer": "viewer"}


class TestConstraints:
    def test_self_loop_rule_rejected_by_database(self, seeded):
        scenario = ThreatScenario.objects.first()
        with pytest.raises(IntegrityError), transaction.atomic():
            PropagationRule.objects.create(scenario=scenario, source=stage("vcs"), target=stage("vcs"), probability=10)

    def test_duplicate_rule_rejected_by_database(self, seeded):
        rule = PropagationRule.objects.first()
        with pytest.raises(IntegrityError), transaction.atomic():
            PropagationRule.objects.create(
                scenario=rule.scenario, source=rule.source, target=rule.target, probability=10
            )

    def test_out_of_range_severity_rejected_by_database(self, seeded):
        with pytest.raises(IntegrityError), transaction.atomic():
            ThreatScenario.objects.filter(slug="malicious-dependency").update(severity=9)

    def test_private_scenario_requires_owner(self, seeded):
        with pytest.raises(IntegrityError), transaction.atomic():
            ThreatScenario.objects.filter(slug="malicious-dependency").update(visibility=Visibility.PRIVATE)


class TestScenarioCrud:
    def test_library_lists_shared_scenarios(self, seeded, viewer_client):
        response = viewer_client.get(reverse("threats:list"))
        assert response.status_code == 200
        assert response.context["page_obj"].paginator.count == 6

    def test_search_and_filters(self, seeded, analyst_client):
        response = analyst_client.get(reverse("threats:list"), {"q": "publishing credential"})
        names = [s.name for s in response.context["page_obj"]]
        assert names == ["Compromised Software Registry"]
        response = analyst_client.get(reverse("threats:list"), {"stage": stage("production").pk})
        assert [s.slug for s in response.context["page_obj"]] == ["production-credential-exposure"]
        response = analyst_client.get(reverse("threats:list"), {"severity": "5"})
        assert all(s.severity == 5 for s in response.context["page_obj"])

    def test_detail_page(self, seeded, viewer_client):
        response = viewer_client.get(reverse("threats:detail", args=["malicious-dependency"]))
        assert response.status_code == 200
        assert b"Propagation graph" in response.content
        assert not response.context["can_edit"]

    def test_analyst_creates_private_scenario(self, seeded, analyst, analyst_client):
        response = analyst_client.post(reverse("threats:create"), scenario_payload(visibility="shared"))
        scenario = ThreatScenario.objects.get(name="Leaked deploy token")
        assert response.status_code == 302
        assert scenario.owner == analyst
        assert scenario.visibility == Visibility.PRIVATE  # cannot self-publish
        assert scenario.rules.count() == 1
        assert list(scenario.controls.values_list("slug", flat=True)) == ["mfa"]
        assert AuditEvent.objects.filter(action=AuditAction.SCENARIO_CREATE).exists()

    def test_create_form_renders_with_default_rules(self, seeded, analyst_client):
        response = analyst_client.get(reverse("threats:create"))
        assert response.status_code == 200
        assert len(response.context["formset"].forms) == 4

    def test_admin_can_create_shared_scenario(self, seeded, admin_client):
        admin_client.post(reverse("threats:create"), scenario_payload(visibility="shared"))
        assert ThreatScenario.objects.get(name="Leaked deploy token").visibility == Visibility.SHARED

    @pytest.mark.parametrize(
        "overrides",
        [{"likelihood": 101}, {"severity": 0}, {"impact": 6}, {"propagation_threshold": 0}, {"name": "   "}],
    )
    def test_invalid_scenario_values_rejected(self, seeded, analyst_client, overrides):
        response = analyst_client.post(reverse("threats:create"), scenario_payload(**overrides))
        assert response.status_code == 200
        assert response.context["form"].errors
        assert not ThreatScenario.objects.filter(is_system=False).exists()

    @pytest.mark.parametrize(
        ("rules", "message"),
        [
            ((("vcs", "vcs", 50),), "itself"),
            ((("vcs", "cicd", 50), ("vcs", "cicd", 60)), "duplicate"),
            ((("registry", "production", 50),), "never be reached"),
        ],
    )
    def test_invalid_graph_rejected(self, seeded, analyst_client, rules, message):
        response = analyst_client.post(reverse("threats:create"), scenario_payload(rules=rules))
        assert response.status_code == 200
        formset = response.context["formset"]
        assert message in str(formset.non_form_errors()) + str(formset.errors)
        assert not ThreatScenario.objects.filter(is_system=False).exists()

    def test_rule_probability_validated(self, seeded, analyst_client):
        response = analyst_client.post(reverse("threats:create"), scenario_payload(rules=(("vcs", "cicd", 140),)))
        assert response.status_code == 200
        assert not ThreatScenario.objects.filter(is_system=False).exists()

    def test_edit_increments_version(self, seeded, analyst, analyst_client):
        analyst_client.post(reverse("threats:create"), scenario_payload())
        scenario = ThreatScenario.objects.get(name="Leaked deploy token")
        rule = scenario.rules.get()
        data = scenario_payload(name="Leaked deploy token v2", existing=1)
        data["rules-0-id"] = rule.pk
        data["rules-0-scenario"] = scenario.pk
        response = analyst_client.post(reverse("threats:edit", args=[scenario.slug]), data)
        assert response.status_code == 302
        scenario.refresh_from_db()
        assert scenario.name == "Leaked deploy token v2"
        assert scenario.version == 2

    def test_archive_and_restore(self, seeded, analyst, analyst_client):
        clone = clone_scenario(ThreatScenario.objects.first(), analyst)
        analyst_client.post(reverse("threats:archive", args=[clone.slug]))
        clone.refresh_from_db()
        assert clone.status == ScenarioStatus.ARCHIVED
        analyst_client.post(reverse("threats:archive", args=[clone.slug]))
        clone.refresh_from_db()
        assert clone.status == ScenarioStatus.ACTIVE

    def test_delete_requires_confirmation_and_post(self, seeded, analyst, analyst_client):
        clone = clone_scenario(ThreatScenario.objects.first(), analyst)
        confirm = analyst_client.get(reverse("threats:delete", args=[clone.slug]))
        assert confirm.status_code == 200
        assert ThreatScenario.objects.filter(pk=clone.pk).exists()
        analyst_client.post(reverse("threats:delete", args=[clone.slug]))
        assert not ThreatScenario.objects.filter(pk=clone.pk).exists()
        assert AuditEvent.objects.filter(action=AuditAction.SCENARIO_DELETE).exists()

    def test_clone_copies_rules_and_controls(self, seeded, analyst, analyst_client):
        source = ThreatScenario.objects.get(slug="malicious-dependency")
        response = analyst_client.post(reverse("threats:clone", args=[source.slug]))
        clone = ThreatScenario.objects.get(owner=analyst)
        assert response.status_code == 302
        assert clone.rules.count() == source.rules.count()
        assert set(clone.controls.all()) == set(source.controls.all())
        assert not clone.is_system and clone.visibility == Visibility.PRIVATE


class TestScenarioPermissions:
    def test_private_scenario_hidden_from_other_users(self, seeded, analyst, client, other_analyst):
        private = clone_scenario(ThreatScenario.objects.first(), analyst)
        client.force_login(other_analyst)
        for name in ("threats:detail", "threats:edit", "threats:delete"):
            assert client.get(reverse(name, args=[private.slug])).status_code == 404, name
        assert client.post(reverse("threats:archive", args=[private.slug])).status_code == 404
        listing = client.get(reverse("threats:list"), {"status": "all"})
        assert private not in list(listing.context["page_obj"])

    def test_admin_cannot_see_other_users_private_scenarios(self, seeded, analyst, admin_client):
        private = clone_scenario(ThreatScenario.objects.first(), analyst)
        assert admin_client.get(reverse("threats:detail", args=[private.slug])).status_code == 404

    def test_analyst_cannot_edit_shared_scenario(self, seeded, analyst_client):
        assert analyst_client.get(reverse("threats:edit", args=["malicious-dependency"])).status_code == 403
        assert analyst_client.post(reverse("threats:archive", args=["malicious-dependency"])).status_code == 403

    def test_system_scenario_cannot_be_deleted_even_by_admin(self, seeded, admin_client):
        assert admin_client.post(reverse("threats:delete", args=["malicious-dependency"])).status_code == 403
        assert ThreatScenario.objects.filter(slug="malicious-dependency").exists()

    def test_admin_can_edit_and_archive_shared_scenario(self, seeded, admin_client):
        assert admin_client.get(reverse("threats:edit", args=["malicious-dependency"])).status_code == 200
        admin_client.post(reverse("threats:archive", args=["malicious-dependency"]))
        assert ThreatScenario.objects.get(slug="malicious-dependency").status == ScenarioStatus.ARCHIVED

    def test_viewer_cannot_create_or_clone(self, seeded, viewer_client):
        assert viewer_client.get(reverse("threats:create")).status_code == 403
        assert viewer_client.post(reverse("threats:create"), scenario_payload()).status_code == 403
        assert viewer_client.post(reverse("threats:clone", args=["malicious-dependency"])).status_code == 403
        assert not ThreatScenario.objects.filter(is_system=False).exists()

    def test_archive_requires_post(self, seeded, admin_client):
        assert admin_client.get(reverse("threats:archive", args=["malicious-dependency"])).status_code == 405


class TestControlLibrary:
    def test_control_list_and_filters(self, seeded, viewer_client):
        response = viewer_client.get(reverse("threats:controls"))
        assert response.status_code == 200
        assert len(response.context["controls"]) == 14
        response = viewer_client.get(reverse("threats:controls"), {"category": "detective"})
        assert {c.category for c in response.context["controls"]} == {"detective"}
        response = viewer_client.get(reverse("threats:controls"), {"stage": "registry"})
        assert all("registry" in [s.key for s in c.stages.all()] for c in response.context["controls"])

    def test_control_detail(self, seeded, viewer_client):
        response = viewer_client.get(reverse("threats:control_detail", args=["mfa"]))
        assert response.status_code == 200
        assert response.context["example_effective"] == 32.0
        assert viewer_client.get(reverse("threats:control_detail", args=["nope"])).status_code == 404
