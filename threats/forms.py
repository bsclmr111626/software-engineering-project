from collections import defaultdict, deque

from django import forms
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory

from accounts.permissions import is_admin
from core.forms import BootstrapFormMixin

from .models import (
    PropagationRule,
    ScenarioStatus,
    SecurityControl,
    SupplyChainStage,
    ThreatScenario,
    Visibility,
)


class ThreatScenarioForm(BootstrapFormMixin, forms.ModelForm):
    controls = forms.ModelMultipleChoiceField(
        queryset=SecurityControl.objects.prefetch_related("stages"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Controls relevant to this scenario. They are highlighted when configuring simulations.",
    )

    class Meta:
        model = ThreatScenario
        fields = [
            "name",
            "description",
            "initial_stage",
            "likelihood",
            "severity",
            "impact",
            "propagation_threshold",
            "visibility",
            "business_impact",
            "asset_categories",
            "assumptions",
            "preventive_measures",
            "detective_measures",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "business_impact": forms.Textarea(attrs={"rows": 2}),
            "assumptions": forms.Textarea(attrs={"rows": 3}),
            "preventive_measures": forms.Textarea(attrs={"rows": 2}),
            "detective_measures": forms.Textarea(attrs={"rows": 2}),
            "likelihood": forms.NumberInput(attrs={"min": 0, "max": 100}),
            "severity": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "impact": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "propagation_threshold": forms.NumberInput(attrs={"min": 1, "max": 100}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["controls"].initial = list(self.instance.controls.values_list("pk", flat=True))
        # Only administrators may publish shared scenarios; the field is removed
        # for everyone else and the service layer forces "private" as well.
        if user is None or not is_admin(user):
            del self.fields["visibility"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name


class PropagationRuleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PropagationRule
        fields = ["source", "target", "probability", "rationale"]
        widgets = {"probability": forms.NumberInput(attrs={"min": 0, "max": 100})}


class BasePropagationRuleFormSet(BaseInlineFormSet):
    """Validates the scenario graph as a whole.

    Rejects self-loops, duplicate edges and rules that can never be reached
    from the scenario's initial stage (an inconsistent configuration).
    """

    initial_stage = None  # set by the view from the validated scenario form

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        edges = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            source, target = form.cleaned_data.get("source"), form.cleaned_data.get("target")
            if source is None or target is None:
                continue
            if source == target:
                raise forms.ValidationError(f"A stage cannot propagate to itself ({source}).")
            if (source, target) in [(s, t) for s, t in edges]:
                raise forms.ValidationError(f"Duplicate propagation rule: {source} → {target}.")
            edges.append((source, target))

        if self.initial_stage is None:
            return
        outgoing = defaultdict(list)
        for source, target in edges:
            outgoing[source].append(target)
        reachable, queue = {self.initial_stage}, deque([self.initial_stage])
        while queue:
            for nxt in outgoing[queue.popleft()]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    queue.append(nxt)
        unreachable = [f"{s} → {t}" for s, t in edges if s not in reachable]
        if unreachable:
            raise forms.ValidationError(
                "These rules can never be reached from the initial stage "
                f"({self.initial_stage}): {', '.join(unreachable)}. Remove them or add a connecting rule."
            )


PropagationRuleFormSet = inlineformset_factory(
    ThreatScenario,
    PropagationRule,
    form=PropagationRuleForm,
    formset=BasePropagationRuleFormSet,
    extra=1,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


def default_rules_for(stage):
    """Initial forward-chain rules suggested for a new custom scenario."""
    later = SupplyChainStage.objects.filter(position__gte=stage.position).order_by("position")
    stages = list(later)
    return [
        {"source": a.pk, "target": b.pk, "probability": 60, "rationale": "Normal forward flow"}
        for a, b in zip(stages, stages[1:], strict=False)
    ]


class ScenarioFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Search scenarios"})
    )
    stage = forms.ModelChoiceField(
        queryset=SupplyChainStage.objects.all(), required=False, empty_label="All entry stages"
    )
    severity = forms.ChoiceField(
        required=False, choices=[("", "Any severity")] + [(str(i), f"Severity ≥ {i}") for i in range(1, 6)]
    )
    status = forms.ChoiceField(
        required=False, choices=[("active", "Active"), ("archived", "Archived"), ("all", "All statuses")]
    )
    visibility = forms.ChoiceField(required=False, choices=[("", "Shared and private")] + list(Visibility.choices))

    def filter(self, queryset):
        if not self.is_valid():
            return queryset.filter(status=ScenarioStatus.ACTIVE)
        data = self.cleaned_data
        if data["q"]:
            queryset = queryset.filter(Q(name__icontains=data["q"]) | Q(description__icontains=data["q"]))
        if data["stage"]:
            queryset = queryset.filter(initial_stage=data["stage"])
        if data["severity"]:
            queryset = queryset.filter(severity__gte=int(data["severity"]))
        status = data["status"] or "active"
        if status != "all":
            queryset = queryset.filter(status=status)
        if data["visibility"]:
            queryset = queryset.filter(visibility=data["visibility"])
        return queryset
