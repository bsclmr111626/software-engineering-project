from django import forms

from core.forms import BootstrapFormMixin

from .models import RemediationItem


class RemediationUpdateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RemediationItem
        fields = ["status", "due_date", "note"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {"note": "Owner, ticket reference, decision rationale or anything a colleague should know."}
