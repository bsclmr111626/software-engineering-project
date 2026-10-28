from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from audit.models import AuditAction
from audit.services import client_ip, record_event

from . import throttling
from .models import Role

LOCKED_MESSAGE = "Too many failed sign-in attempts. Wait {minutes} minutes and try again."


class ThrottledAuthenticationForm(AuthenticationForm):
    """The standard sign-in form, refused before the password is checked once
    the username or client IP has too many recent failures (see throttling.py)."""

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if throttling.is_locked(username, client_ip(self.request)):
            record_event(None, AuditAction.LOGIN_THROTTLED, request=self.request, attempted_username=username)
            raise forms.ValidationError(
                LOCKED_MESSAGE.format(minutes=settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES), code="throttled"
            )
        return super().clean()


class RegistrationForm(UserCreationForm):
    """Public sign-up form. It deliberately has no role field: the role is
    assigned on the server (CODEGUARD_DEFAULT_ROLE) and can never be admin."""

    email = forms.EmailField(required=True, help_text="Used for password reset emails.")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if settings.CODEGUARD_REGISTRATION == "domain":
            domain = email.rpartition("@")[2]
            if domain not in settings.CODEGUARD_REGISTRATION_DOMAINS:
                raise forms.ValidationError("Registration is limited to your organization's email domains.")
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices)
