from django.conf import settings
from django.db import models
from django.db.models import Q, Sum

from apps.bookings.models import Booking, CancellationRequest
from apps.common import MONEY, TimeStampedModel


class PaymentTransaction(TimeStampedModel):
    """A gateway order for a booking. Stores gateway IDs and status only, never card/UPI/bank details."""

    class Status(models.TextChoices):
        CREATED = "created", "Order created"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20, default="razorpay")
    gateway_order_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED, db_index=True)
    is_live = models.BooleanField(default=False)
    signature_verified = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=255, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive")]

    def refundable_amount(self):
        if self.status != self.Status.CAPTURED:
            return 0
        committed = self.refunds.exclude(status=Refund.Status.FAILED).aggregate(s=Sum("amount"))["s"] or 0
        return self.amount - committed

    def __str__(self):
        return self.gateway_order_id


class GatewayEvent(models.Model):
    """Every webhook received. Unique event_id makes processing idempotent."""

    gateway = models.CharField(max_length=20)
    event_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    signature_valid = models.BooleanField()
    transaction = models.ForeignKey(
        PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["gateway", "event_id"], name="uniq_gateway_event")]


class Refund(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    payment = models.ForeignKey(PaymentTransaction, on_delete=models.PROTECT, related_name="refunds")
    cancellation_request = models.ForeignKey(
        CancellationRequest, on_delete=models.PROTECT, null=True, blank=True, related_name="refunds"
    )
    amount = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    gateway_refund_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="refund_amount_positive")]
