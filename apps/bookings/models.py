from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common import MONEY, TimeStampedModel, make_reference
from apps.fleet.models import Seat
from apps.schedules.models import Fare, Schedule


def booking_reference():
    return make_reference("SB")


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        CONFIRMED = "confirmed", "Confirmed"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=12, unique=True, default=booking_reference, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="bookings"
    )
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, related_name="bookings")
    fare = models.ForeignKey(Fare, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    passenger_count = models.PositiveIntegerField()
    # Snapshot of price at booking time, computed on the server. Never taken from the client.
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    base_amount = models.DecimalField(**MONEY)
    tax_amount = models.DecimalField(**MONEY)
    fee_amount = models.DecimalField(**MONEY)
    total_amount = models.DecimalField(**MONEY)
    fare_snapshot = models.JSONField(default=dict)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(passenger_count__gt=0), name="booking_passengers_positive"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="booking_total_non_negative"),
        ]

    def __str__(self):
        return self.reference


class BookingStatusHistory(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "booking status history"


class BookingPassenger(models.Model):
    # ponytail: name/age/gender only; add ID document fields when an operator's manifest rules require them.
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        UNDISCLOSED = "undisclosed", "Prefer not to say"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="passengers")
    full_name = models.CharField(max_length=150)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.UNDISCLOSED)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(age__lte=120), name="passenger_age_realistic")]

    def __str__(self):
        return self.full_name


class BookingSeat(models.Model):
    """Assigned-seat allocations. Only used for vessels with assigned seating.

    active_schedule equals schedule while the allocation is live and is NULL once
    released, so the unique constraint blocks double-allocation on every DB
    (MySQL has no partial unique indexes, but ignores NULLs in unique keys).
    """

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="seats")
    passenger = models.OneToOneField(
        BookingPassenger, on_delete=models.CASCADE, null=True, blank=True, related_name="seat"
    )
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, related_name="+")
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, related_name="allocations")
    active_schedule = models.ForeignKey(
        Schedule, on_delete=models.PROTECT, null=True, blank=True, related_name="active_seat_allocations"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["active_schedule", "seat"], name="uniq_active_seat")]

    def release(self):
        self.active_schedule = None
        self.save(update_fields=["active_schedule"])


class CancellationRule(models.Model):
    """One refund band of an approved cancellation policy, e.g. '48+ hours before departure: 90%'.

    Entered by an admin from the business's approved terms. The band with the largest
    min_hours_before_departure that the passenger still meets applies.
    """

    policy = models.ForeignKey(
        "compliance.PolicyVersion", on_delete=models.CASCADE, related_name="cancellation_rules",
        limit_choices_to={"policy_type": "cancellation"},
    )
    min_hours_before_departure = models.PositiveIntegerField()
    refund_percent = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-min_hours_before_departure"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "min_hours_before_departure"], name="uniq_rule_band"),
            models.CheckConstraint(condition=Q(refund_percent__lte=100), name="refund_percent_max_100"),
        ]

    def __str__(self):
        return f"{self.min_hours_before_departure}+ h before departure: {self.refund_percent}%"


class CancellationRequest(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="cancellation_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    # Computed from the approved, published policy in force when the request was made.
    eligible_refund_amount = models.DecimalField(**MONEY, default=0)
    policy_version = models.ForeignKey(
        "compliance.PolicyVersion", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(eligible_refund_amount__gte=0), name="cancel_refund_non_negative"),
        ]
