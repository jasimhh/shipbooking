from django import forms

from apps.accounts.forms import NoColon, phone_validator

from .models import BookingPassenger

MAX_PASSENGERS = 9


class TripForm(NoColon, forms.Form):
    fare = forms.ModelChoiceField(queryset=None, label="Class", widget=forms.RadioSelect, empty_label=None)
    contact_email = forms.EmailField(label="Email for your tickets")
    contact_phone = forms.CharField(label="Mobile number", validators=[phone_validator],
                                    help_text="Used only for updates about this journey.")

    def __init__(self, *args, schedule, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fare"].queryset = schedule.fares.select_related("cabin_class").order_by("base_fare")
        self.fields["fare"].label_from_instance = lambda f: f.cabin_class.name


class PassengerForm(NoColon, forms.Form):
    full_name = forms.CharField(label="Full name", max_length=150)
    age = forms.IntegerField(label="Age", min_value=0, max_value=120)
    gender = forms.ChoiceField(label="Gender", choices=BookingPassenger.Gender.choices,
                               initial=BookingPassenger.Gender.UNDISCLOSED)


PassengerFormSet = forms.formset_factory(
    PassengerForm, extra=0, min_num=1, max_num=MAX_PASSENGERS, validate_min=True, validate_max=True,
)
