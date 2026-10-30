import secrets

from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from apps.common import make_reference


def ticket_number():
    return make_reference("TK", 10)


def new_verification_token():
    return secrets.token_urlsafe(24)


class Ticket(models.Model):
    """An issued e-ticket. Reissue voids the old ticket and creates a new one.

    The QR code encodes only verification_token, never personal data.
    """

    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        BOARDED = "boarded", "Boarded"
        VOID = "void", "Void"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="tickets")
    number = models.CharField(max_length=12, unique=True, default=ticket_number, editable=False)
    verification_token = models.CharField(max_length=64, unique=True, default=new_verification_token, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VALID, db_index=True)
    pdf = models.FileField(upload_to="tickets/", blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.number


class TicketVerificationEvent(models.Model):
    class Result(models.TextChoices):
        VALID = "valid", "Valid"
        ALREADY_BOARDED = "already_boarded", "Already boarded"
        VOID = "void", "Void"
        NOT_FOUND = "not_found", "Not found"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name="verifications")
    result = models.CharField(max_length=20, choices=Result.choices)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
