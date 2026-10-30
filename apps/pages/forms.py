from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.fleet.models import Port
from apps.support.models import SupportTicket


MAX_PASSENGERS = 9
BOOKING_WINDOW_DAYS = 365


class SiteForm(forms.Form):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class SearchForm(SiteForm):
    origin = forms.ModelChoiceField(
        Port.objects.filter(is_active=True), to_field_name="code", label="From", empty_label="Select departure port"
    )
    destination = forms.ModelChoiceField(
        Port.objects.filter(is_active=True), to_field_name="code", label="To", empty_label="Select destination"
    )
    date = forms.DateField(label="Travel date", widget=forms.DateInput(attrs={"type": "date"}))
    passengers = forms.IntegerField(label="Passengers", min_value=1, max_value=MAX_PASSENGERS, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["date"].widget.attrs.update(
            min=today.isoformat(), max=(today + timedelta(days=BOOKING_WINDOW_DAYS)).isoformat()
        )

    def clean_date(self):
        date = self.cleaned_data["date"]
        today = timezone.localdate()
        if date < today:
            raise forms.ValidationError("Choose today or a later date.")
        if date > today + timedelta(days=BOOKING_WINDOW_DAYS):
            raise forms.ValidationError(f"Sailings can be searched up to {BOOKING_WINDOW_DAYS} days ahead.")
        return date

    def clean(self):
        data = super().clean()
        if data.get("origin") and data.get("origin") == data.get("destination"):
            self.add_error("destination", "Destination must be different from the departure port.")
        return data


class ContactForm(SiteForm):
    email = forms.EmailField(label="Your email")
    category = forms.ChoiceField(label="Topic", choices=SupportTicket.Category.choices)
    booking_reference = forms.CharField(label="Booking reference (if any)", max_length=12, required=False)
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}), max_length=5000)
    # Hidden from people, filled by naive bots.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_booking_reference(self):
        return self.cleaned_data["booking_reference"].strip().upper()
