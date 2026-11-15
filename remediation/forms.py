from django import forms

from core.forms import BootstrapFormMixin

from .models import RemediationItem


class RemediationUpdateForm(BootstrapFormMixin, forms.ModelForm):
    evidence_url = forms.URLField(
        label="Evidence link",
        required=False,
        max_length=500,
        assume_scheme="https",
        help_text="A ticket, pull request or document that shows the work, for example a Jira or GitHub link.",
        widget=forms.URLInput(attrs={"placeholder": "https://"}),
    )

    class Meta:
        model = RemediationItem
        fields = ["status", "due_date", "evidence_url", "note"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {"note": "Decision rationale, scope, or anything a colleague should know."}

    def clean_evidence_url(self):
        url = self.cleaned_data["evidence_url"]
        if url and not url.lower().startswith(("https://", "http://")):
            raise forms.ValidationError("Use a web link that starts with https://.")
        return url


class AssignForm(BootstrapFormMixin, forms.Form):
    assignee = forms.ModelChoiceField(queryset=None, required=False, empty_label="Nobody yet", label="Assigned to")
    is_shared = forms.BooleanField(
        required=False,
        label="Visible to everyone in the workspace",
        help_text="Off: only the person who added it and the assignee can see it.",
    )

    def __init__(self, *args, choices, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = choices
        self.fields["assignee"].label_from_instance = lambda u: (
            f"{u.get_full_name()} (@{u.get_username()})" if u.get_full_name() else u.get_username()
        )


class CommentForm(BootstrapFormMixin, forms.Form):
    comment = forms.CharField(
        label="Add a comment",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
