"""Forms for the settings center. Each preference form edits one page's
fields of UserPreference, so a page can never overwrite another's values."""

from django import forms
from django.contrib.auth import get_user_model

from core.forms import BootstrapFormMixin

from .models import Profile, UserPreference, Workspace


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    """Name fields live on the User model, professional details on Profile."""

    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")

    class Meta:
        model = Profile
        fields = ["job_title", "team"]
        labels = {"job_title": "Job title", "team": "Team"}
        help_texts = {
            "job_title": "Shown on your profile, for example “Application security engineer”.",
            "team": "The team or function you work in.",
        }

    field_order = ["first_name", "last_name", "job_title", "team"]

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["job_title"].widget.attrs["autocomplete"] = "organization-title"

    def save(self, commit=True):
        profile = super().save(commit=commit)
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            self.user.save(update_fields=["first_name", "last_name"])
        return profile


class EmailChangeForm(BootstrapFormMixin, forms.Form):
    """Changing the address used for password resets needs the current
    password, so a briefly unattended session cannot redirect resets."""

    email = forms.EmailField(label="New email address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    current_password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Required to confirm that it is you.",
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email == (self.user.email or "").lower():
            raise forms.ValidationError("This is already your email address.")
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password is incorrect.")
        return password


class CloseAccountForm(BootstrapFormMixin, forms.Form):
    """Closing an account needs the current password and an explicit tick,
    so neither an unattended session nor a stray click can do it."""

    current_password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(
        label="I understand that my account will be closed now and deleted with my work after the waiting period",
        error_messages={"required": "Tick the box to confirm."},
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password is incorrect.")
        return password


class CurrentPasswordForm(BootstrapFormMixin, forms.Form):
    """Asks for the current password before a change to how the account signs in."""

    current_password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password is incorrect.")
        return password


class TwoFactorSetupForm(CurrentPasswordForm):
    """Turning two-step sign-in on: the password, and a code from the app to
    prove it was set up with the key shown."""

    code = forms.CharField(
        label="Six-digit code from the app",
        max_length=8,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )

    def __init__(self, *args, secret, **kwargs):
        self.secret = secret
        self.step = None
        super().__init__(*args, **kwargs)

    def clean_code(self):
        from . import two_factor

        self.step = two_factor.matching_step(self.secret, self.cleaned_data["code"])
        if self.step is None:
            raise forms.ValidationError(
                "That code does not match. Check that the app added the CodeGuard entry and that "
                "your device's clock is set automatically, then try the newest code."
            )
        return self.cleaned_data["code"]


class WorkspaceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ["name"]
        labels = {"name": "Workspace name"}
        help_texts = {"name": "Shown to members and in invitation emails."}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Enter a name.")
        return name


class PreferenceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = []


def _radios(*names):
    return {name: forms.RadioSelect for name in names}


class AppearanceForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["color_mode", "surface", "accent"]
        widgets = _radios("color_mode", "surface", "accent")
        labels = {"color_mode": "Color mode", "surface": "Surfaces", "accent": "Theme"}


class TypographyForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["text_size", "heading_font"]
        widgets = _radios("text_size", "heading_font")
        labels = {"text_size": "Text size", "heading_font": "Heading typeface"}


class DisplayForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["density", "timestamp_style", "page_size", "start_page"]
        widgets = _radios("density", "timestamp_style")
        labels = {
            "density": "Layout density",
            "timestamp_style": "Timestamps",
            "page_size": "Rows per page",
            "start_page": "Start page after signing in",
        }
        help_texts = {
            "page_size": "Used by reports, results, the threat library, remediation and the audit log.",
        }


class AccessibilityForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["reduce_motion", "increase_contrast", "underline_links"]
        labels = {
            "reduce_motion": "Reduce motion",
            "increase_contrast": "Increase contrast",
            "underline_links": "Always underline links",
        }
        help_texts = {
            "reduce_motion": "Turns off transitions and animated scrolling. Your device's reduced-motion setting is always respected.",
            "increase_contrast": "Darker secondary text and stronger borders and focus outlines.",
            "underline_links": "Underlines every link, including names in tables and navigation lists.",
        }


class NotificationForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["notify_shared_reports", "notify_remediation_due", "notify_account_security"]
        labels = {
            "notify_shared_reports": "Reports shared by colleagues",
            "notify_remediation_due": "Remediation assignments and due dates",
            "notify_account_security": "Account security events",
        }
        help_texts = {
            "notify_shared_reports": "When a colleague shares a simulation report with your workspace.",
            "notify_remediation_due": "When a colleague assigns you an item (also by email), and your open items that are overdue or due within 7 days.",
            "notify_account_security": "Password and email changes, role changes, signed-out sessions and failed sign-ins to your account.",
        }


class PrivacyForm(PreferenceForm):
    class Meta:
        model = UserPreference
        fields = ["share_reports_by_default"]
        labels = {"share_reports_by_default": "Share new reports with my workspace"}
        help_texts = {
            "share_reports_by_default": "When on, each completed simulation you run is shared read-only with the "
            "members of your workspace as soon as it finishes. You can make any report private again from the report.",
        }
