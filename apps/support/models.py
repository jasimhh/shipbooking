from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from apps.common import TimeStampedModel, make_reference


class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    IN_APP = "in_app", "In-app"


class NotificationTemplate(TimeStampedModel):
    key = models.SlugField(max_length=60)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(help_text="Django template syntax, e.g. {{ booking.reference }}")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "channel"], name="uniq_template_key_channel")]

    def __str__(self):
        return f"{self.key} ({self.channel})"


class Notification(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=254)
    template_key = models.SlugField(max_length=60)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)


def support_reference():
    return make_reference("ST")


class SupportTicket(TimeStampedModel):
    class Category(models.TextChoices):
        BOOKING = "booking", "Booking help"
        PAYMENT = "payment", "Payment issue"
        CANCELLATION = "cancellation", "Cancellation or refund"
        COMPLAINT = "complaint", "Complaint"
        GRIEVANCE = "grievance", "Grievance"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        AWAITING_CUSTOMER = "awaiting_customer", "Awaiting customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    reference = models.CharField(max_length=12, unique=True, default=support_reference, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets"
    )
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    contact_email = models.EmailField()
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.reference


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_staff_reply = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
