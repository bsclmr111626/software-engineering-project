"""The "Get started" checklist on the Overview page.

Each step is worked out from data that already exists (runs, remediation
items, members, two-step sign-in), so it ticks itself off as people use the
product and can never disagree with what they have actually done. Nothing
here is stored except the moment someone hides the checklist
(``UserPreference.onboarding_dismissed_at``).
"""

from dataclasses import dataclass

from django.urls import reverse

from accounts import two_factor
from accounts.models import Invitation
from accounts.permissions import can_run_simulations, is_admin
from accounts.preferences import preferences_for
from accounts.workspaces import members, workspace_of
from remediation.models import RemediationItem
from simulation.models import RunStatus, SimulationRun


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    detail: str
    url: str
    action: str
    done: bool


def steps(user):
    """The steps that apply to ``user``'s role, in order."""
    found = []
    if can_run_simulations(user):
        runs = SimulationRun.objects.filter(user=user, status=RunStatus.COMPLETED)
        found += [
            Step(
                "simulate",
                "Run your first simulation",
                "Pick a threat scenario and see how far a compromise spreads through the five stages.",
                reverse("simulation:configure"),
                "New simulation",
                runs.exists(),
            ),
            Step(
                "controls",
                "Run it again with controls",
                "Enable security controls and compare: the report shows how much risk they remove.",
                reverse("simulation:configure"),
                "Choose controls",
                any(run.enabled_controls for run in runs.only("enabled_controls")[:50]),
            ),
            Step(
                "plan",
                "Commit to a fix",
                "From a report's recommendations, choose Add to plan to track the control as remediation work.",
                reverse("simulation:results") + "?scope=mine",
                "Open your results",
                RemediationItem.objects.filter(owner=user).exists(),
            ),
        ]
    else:
        found.append(
            Step(
                "read",
                "Read how the model works",
                "Your role reads reports your colleagues share. The methodology explains every number in them.",
                reverse("core:help"),
                "Open the methodology",
                False,
            )
        )
    if is_admin(user):
        workspace = workspace_of(user)
        found.append(
            Step(
                "invite",
                "Invite your team",
                f"Add colleagues to the {workspace.name} workspace and give each a role.",
                reverse("settings:users"),
                "Invite people",
                members(workspace).count() > 1
                or Invitation.objects.filter(
                    workspace=workspace, accepted_at__isnull=True, revoked_at__isnull=True
                ).exists(),
            )
        )
    found.append(
        Step(
            "secure",
            "Turn on two-step sign-in",
            "Ask for a code from your phone after your password, so a stolen password alone is not enough.",
            reverse("settings:two_factor_setup"),
            "Set it up",
            two_factor.enabled(user),
        )
    )
    return found


def checklist(user):
    """What the Overview page needs: the steps, progress, and whether to show it."""
    all_steps = steps(user)
    done = sum(step.done for step in all_steps)
    dismissed = preferences_for(user).onboarding_dismissed_at is not None
    complete = done == len(all_steps)
    return {
        "steps": all_steps,
        "done": done,
        "total": len(all_steps),
        "next": next((step for step in all_steps if not step.done), None),
        "visible": not dismissed and not complete,
        "hidden_but_incomplete": dismissed and not complete,
    }
