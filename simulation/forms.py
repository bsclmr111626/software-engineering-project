from django import forms

from core.forms import BootstrapFormMixin
from threats.models import ScenarioStatus, SecurityControl


class SimulationForm(BootstrapFormMixin, forms.Form):
    """Simulation configuration. All values are re-validated on the server."""

    scenario = forms.ModelChoiceField(queryset=None, empty_label="Choose a scenario")
    likelihood = forms.IntegerField(min_value=0, max_value=100, label="Base likelihood (%)")
    severity = forms.IntegerField(min_value=1, max_value=5, label="Severity (1-5)")
    impact = forms.IntegerField(min_value=1, max_value=5, label="Business impact (1-5)")
    threshold = forms.IntegerField(min_value=1, max_value=100, label="Propagation threshold (%)")
    controls = forms.ModelMultipleChoiceField(
        queryset=SecurityControl.objects.prefetch_related("stages").order_by("category", "name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Enabled security controls",
    )

    def __init__(self, *args, scenarios=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active scenarios the user is allowed to see can be selected,
        # so a forged POST cannot run another user's private scenario.
        self.fields["scenario"].queryset = scenarios.filter(status=ScenarioStatus.ACTIVE)
        self.fields["scenario"].to_field_name = "slug"
