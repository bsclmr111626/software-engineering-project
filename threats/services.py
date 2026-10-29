"""Business rules for threat scenarios: visibility, ownership and persistence.

Ownership rules
---------------
* Shared scenarios (including the seeded system scenarios) are visible to all
  authenticated users. Private scenarios are visible only to their owner.
* Analysts may edit, archive and delete their own private scenarios.
* Administrators may additionally manage shared scenarios.
* System (seeded) scenarios can be archived but never deleted.
"""

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from accounts.permissions import can_manage_scenarios, is_admin

from .models import PropagationRule, ScenarioControl, ScenarioStatus, ThreatScenario, Visibility


def visible_scenarios(user):
    return ThreatScenario.objects.filter(Q(visibility=Visibility.SHARED) | Q(owner=user)).select_related(
        "initial_stage", "owner"
    )


def get_visible_scenario(user, slug):
    """Return the scenario or raise 404, so private slugs are not disclosed."""
    try:
        return visible_scenarios(user).get(slug=slug)
    except ThreatScenario.DoesNotExist:
        raise Http404("Scenario not found.") from None


def can_edit(user, scenario):
    if not can_manage_scenarios(user):
        return False
    if scenario.visibility == Visibility.SHARED:
        return is_admin(user)
    return scenario.owner_id == user.pk


def can_delete(user, scenario):
    return not scenario.is_system and can_edit(user, scenario)


def unique_slug(name):
    base = slugify(name)[:60] or "scenario"
    slug = base
    while ThreatScenario.objects.filter(slug=slug).exists():
        slug = f"{base}-{get_random_string(6, 'abcdefghijklmnopqrstuvwxyz0123456789')}"
    return slug


@transaction.atomic
def save_scenario(form, rule_formset, user):
    """Create or update a scenario, its propagation rules and controls atomically."""
    scenario = form.save(commit=False)
    creating = scenario.pk is None
    if creating:
        scenario.slug = unique_slug(scenario.name)
        scenario.owner = user
    else:
        scenario.version += 1
    if not is_admin(user):
        scenario.visibility = Visibility.PRIVATE
    scenario.save()

    rule_formset.instance = scenario
    rule_formset.save()

    selected = set(form.cleaned_data["controls"])
    scenario.scenario_controls.exclude(control__in=selected).delete()
    existing = set(scenario.scenario_controls.values_list("control_id", flat=True))
    ScenarioControl.objects.bulk_create(
        ScenarioControl(scenario=scenario, control=c) for c in selected if c.pk not in existing
    )
    return scenario, creating


@transaction.atomic
def clone_scenario(scenario, user):
    """Copy a visible scenario into a new private scenario owned by ``user``."""
    rules = list(scenario.rules.all())
    links = list(scenario.scenario_controls.all())
    clone = ThreatScenario.objects.get(pk=scenario.pk)
    clone.pk = None
    clone.name = f"{scenario.name} (copy)"[:120]
    clone.slug = unique_slug(clone.name)
    clone.owner = user
    clone.visibility = Visibility.PRIVATE
    clone.status = ScenarioStatus.ACTIVE
    clone.is_system = False
    clone.version = 1
    clone.save()
    PropagationRule.objects.bulk_create(
        PropagationRule(
            scenario=clone,
            source_id=r.source_id,
            target_id=r.target_id,
            probability=r.probability,
            rationale=r.rationale,
        )
        for r in rules
    )
    ScenarioControl.objects.bulk_create(
        ScenarioControl(scenario=clone, control_id=link.control_id, note=link.note) for link in links
    )
    return clone
