from django import forms
from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from audit.models import AuditAction
from audit.services import client_ip, record_event
from core.forms import BootstrapFormMixin

from . import throttling
from .models import Role

LOCKED_MESSAGE = "Too many failed sign-in attempts. Wait {minutes} minutes and try again."
UNVERIFIED_MESSAGE = "Confirm your email address before signing in: open the link we sent when you registered."


class ThrottledLoginMixin:
    """Refuses a sign-in before the password is checked once the username or
    client IP has too many recent failures (see throttling.py), and refuses
    self-registered accounts whose email address is not confirmed yet."""

    needs_verification = False

    def clean(self):
        username = throttling.canonical_username((self.cleaned_data.get("username") or "").strip())
        if throttling.is_locked(username, client_ip(self.request)):
            record_event(None, AuditAction.LOGIN_THROTTLED, request=self.request, attempted_username=username)
            raise forms.ValidationError(
                LOCKED_MESSAGE.format(minutes=settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES), code="throttled"
            )
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        profile = getattr(user, "profile", None)
        if profile is not None and profile.must_verify_before_sign_in:
            # Reached only with the right password, so it reveals nothing to a guesser.
            self.needs_verification = True
            raise forms.ValidationError(UNVERIFIED_MESSAGE, code="unverified")


class ThrottledAuthenticationForm(ThrottledLoginMixin, AuthenticationForm):
    """The standard sign-in form with the sign-in limits applied. The username
    field also accepts an email address (accounts/backends.py)."""


class ThrottledAdminAuthenticationForm(ThrottledLoginMixin, AdminAuthenticationForm):
    """The Django admin sign-in form with the same limits, so /admin/login/
    cannot be used to guess passwords without the lockout (accounts/admin.py)."""


class TermsMixin(forms.Form):
    accept_terms = forms.BooleanField(
        required=True,
        label="I have read the terms of use and the privacy notice",
        error_messages={"required": "Please confirm that you have read the terms of use and the privacy notice."},
    )


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    """Public sign-up form. It deliberately has no role field: the role is
    assigned on the server (CODEGUARD_DEFAULT_ROLE) and can never be admin.

    It does not say whether an email address is already registered; the view
    emails the owner of that address instead (accounts/views.register).
    ``website`` is a honeypot: people never see it, simple bots fill it in.
    """

    first_name = forms.CharField(
        max_length=150, label="First name", widget=forms.TextInput(attrs={"autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        max_length=150, required=False, label="Last name", widget=forms.TextInput(attrs={"autocomplete": "family-name"})
    )
    email = forms.EmailField(
        label="Work email",
        help_text="We will send a link to confirm it. It is also where password reset links go.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    accept_terms = TermsMixin.base_fields["accept_terms"]
    website = forms.CharField(required=False, label="Leave this field empty")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("first_name", "last_name", "username", "email")

    field_order = ["first_name", "last_name", "email", "username", "password1", "password2", "accept_terms", "website"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if settings.CODEGUARD_REGISTRATION == "domain":
            domain = email.rpartition("@")[2]
            if domain not in settings.CODEGUARD_REGISTRATION_DOMAINS:
                raise forms.ValidationError("Registration is limited to your organization's email domains.")
        return email

    @property
    def is_bot(self):
        return bool(self.cleaned_data.get("website"))


class EmailForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices)


class InvitationForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "off"}))
    role = forms.ChoiceField(choices=Role.choices, initial=Role.ANALYST, label="Role")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email


class AcceptInvitationForm(BootstrapFormMixin, TermsMixin, forms.Form):
    """Creates the invited account. The email address comes from the
    invitation and cannot be changed here; the person picks the rest."""

    first_name = forms.CharField(
        max_length=150, label="First name", widget=forms.TextInput(attrs={"autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        max_length=150, required=False, label="Last name", widget=forms.TextInput(attrs={"autocomplete": "family-name"})
    )
    username = forms.CharField(
        max_length=150,
        label="Username",
        help_text="Letters, digits and @/./+/-/_ only. You can also sign in with your email address.",
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    password1 = forms.CharField(
        label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    field_order = ["first_name", "last_name", "username", "password1", "password2", "accept_terms"]

    def __init__(self, *args, invitation, **kwargs):
        self.invitation = invitation
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = password_validation.password_validators_help_text_html()

    def clean_username(self):
        User = get_user_model()
        username = User.normalize_username(self.cleaned_data["username"].strip())
        User.username_validator(username)
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is taken. Choose another.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            candidate = get_user_model()(
                username=cleaned.get("username", ""),
                email=self.invitation.email,
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                password_validation.validate_password(p1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned


class UserFilterForm(forms.Form):
    STATUS_CHOICES = [
        ("", "All statuses"),
        ("active", "Active"),
        ("unverified", "Email not confirmed"),
        ("suspended", "Suspended"),
    ]
    q = forms.CharField(required=False, label="Search", max_length=100)
    role = forms.ChoiceField(required=False, choices=[("", "All roles"), *Role.choices], label="Role")
    status = forms.ChoiceField(required=False, choices=STATUS_CHOICES, label="Status")
