"""Populate stages, the control catalog and the system threat scenarios.

Safe to run repeatedly: records are matched by their stable key/slug, so no
duplicates are created. Stages and controls are updated to match the seed
definitions. Existing system scenarios are left untouched (an administrator
may have edited them) unless ``--reset-scenarios`` is passed.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Profile, Role
from threats.models import (
    PropagationRule,
    ScenarioControl,
    SecurityControl,
    SupplyChainStage,
    ThreatScenario,
    Visibility,
)
from threats.seed_data import CONTROL_NOTES, CONTROLS, SCENARIOS, STAGES

DEMO_USERS = [
    ("demo_admin", Role.ADMIN),
    ("demo_analyst", Role.ANALYST),
    ("demo_viewer", Role.VIEWER),
]
DEMO_PASSWORD = "CodeGuard-demo-2024"  # development-only, refused unless DEBUG


class Command(BaseCommand):
    help = "Seed CodeGuard reference data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-scenarios",
            action="store_true",
            help="Overwrite system scenarios, rules and control links with the seed definitions.",
        )
        parser.add_argument(
            "--demo-users",
            action="store_true",
            help="Create development-only demo accounts (requires DJANGO_DEBUG=true).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        stages = {}
        for data in STAGES:
            stage, _ = SupplyChainStage.objects.update_or_create(key=data["key"], defaults=data)
            stages[stage.key] = stage

        controls = {}
        for slug, name, category, stage_keys, eff, effort, priority, description, addresses in CONTROLS:
            control, _ = SecurityControl.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "category": category,
                    "effectiveness": eff,
                    "effort": effort,
                    "priority": priority,
                    "description": description,
                    "addresses": addresses,
                    "effectiveness_basis": CONTROL_NOTES[slug][0],
                    "limitations": CONTROL_NOTES[slug][1],
                },
            )
            control.stages.set([stages[k] for k in stage_keys])
            controls[slug] = control

        created_count = 0
        for data in SCENARIOS:
            fields = {k: v for k, v in data.items() if k not in {"slug", "rules", "controls", "initial_stage"}}
            fields.update(
                initial_stage=stages[data["initial_stage"]],
                visibility=Visibility.SHARED,
                is_system=True,
                owner=None,
            )
            scenario = ThreatScenario.objects.filter(slug=data["slug"]).first()
            if scenario is None:
                scenario = ThreatScenario.objects.create(slug=data["slug"], **fields)
                created_count += 1
            elif options["reset_scenarios"]:
                for key, value in fields.items():
                    setattr(scenario, key, value)
                scenario.version += 1
                scenario.save()
                scenario.rules.all().delete()
                scenario.scenario_controls.all().delete()
            else:
                continue
            PropagationRule.objects.bulk_create(
                PropagationRule(scenario=scenario, source=stages[s], target=stages[t], probability=p, rationale=r)
                for s, t, p, r in data["rules"]
            )
            ScenarioControl.objects.bulk_create(
                ScenarioControl(scenario=scenario, control=controls[c]) for c in data["controls"]
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(stages)} stages, {len(controls)} controls, "
                f"{created_count} new system scenarios ({ThreatScenario.objects.filter(is_system=True).count()} total)."
            )
        )

        if options["demo_users"]:
            self._create_demo_users()

    def _create_demo_users(self):
        if not settings.DEBUG:
            raise CommandError("Demo users are development-only. Set DJANGO_DEBUG=true to create them.")
        User = get_user_model()
        for username, role in DEMO_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            Profile.objects.update_or_create(user=user, defaults={"role": role})
        self.stdout.write(
            self.style.WARNING(
                "Demo users ready (development only): demo_admin, demo_analyst, demo_viewer. "
                "The shared password is documented in README.md."
            )
        )
