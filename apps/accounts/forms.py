from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm, UserCreationForm,
)
from django.core.validators import RegexValidator

from .models import User

phone_validator = RegexValidator(r"^\+?[0-9 ]{7,15}$", "Enter a phone number using digits, spaces and an optional +.")


class NoColon:
    """Drop Django's default ':' after labels."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class EmailLoginForm(NoColon, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget = forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True})


class RegistrationForm(NoColon, UserCreationForm):
    phone = forms.CharField(label="Mobile number (optional)", required=False, validators=[phone_validator])

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone"]
        field_classes = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["first_name"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in or resetting your password.")
        return email


class ProfileForm(NoColon, forms.ModelForm):
    phone = forms.CharField(label="Mobile number", required=False, validators=[phone_validator])

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True


class ResetForm(NoColon, PasswordResetForm):
    pass


class NewPasswordForm(NoColon, SetPasswordForm):
    pass


class ChangePasswordForm(NoColon, PasswordChangeForm):
    pass
