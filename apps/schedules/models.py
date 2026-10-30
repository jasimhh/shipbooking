from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from django.utils import timezone

from apps.common import MONEY, TimeStampedModel
from apps.fleet.models import CabinClass, Route, Vessel
from apps.operators.models import Operator


class ScheduleQuerySet(models.QuerySet):
    def public(self):
        """Sailings the public may view (not drafts)."""
        return self.exclude(status=Schedule.Status.DRAFT)

    def bookable(self):
        """Published sailings that are open for booking right now."""
        now = timezone.now()
        return self.filter(
            status__in=[Schedule.Status.PUBLISHED, Schedule.Status.DELAYED],
            departure_at__gt=now,
            route__is_active=True,
            vessel__is_active=True,
            route__operator__is_active=True,
            route__operator__verification_status=Operator.Verification.VERIFIED,
        ).filter(Q(booking_closes_at__isnull=True) | Q(booking_closes_at__gt=now))


class Schedule(TimeStampedModel):
    """One sailing: a vessel on a route at a time."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        DELAYED = "delayed", "Delayed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="schedules")
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name="schedules")
    departure_at = models.DateTimeField()
    arrival_at = models.DateTimeField()
    booking_closes_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    status_note = models.TextField(blank=True)

    objects = ScheduleQuerySet.as_manager()

    class Meta:
        ordering = ["departure_at"]
        indexes = [models.Index(fields=["route", "departure_at", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(arrival_at__gt=F("departure_at")), name="arrival_after_departure"),
        ]

    def clean(self):
        if self.route_id and self.vessel_id and self.route.operator_id != self.vessel.operator_id:
            raise ValidationError("Vessel and route must belong to the same operator.")

    @property
    def operator(self):
        return self.route.operator

    @property
    def duration(self):
        return self.arrival_at - self.departure_at

    def __str__(self):
        return f"{self.route} {self.departure_at:%Y-%m-%d %H:%M}"


class Fare(TimeStampedModel):
    """Price and inventory for one cabin class on one sailing.

    units_allocated counts held + confirmed places. The check constraint is the
    last line of defence against overselling; allocation code also locks the row.
    """

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="fares")
    cabin_class = models.ForeignKey(CabinClass, on_delete=models.PROTECT, related_name="fares")
    base_fare = models.DecimalField(**MONEY)
    tax_amount = models.DecimalField(**MONEY, default=0)
    fee_amount = models.DecimalField(**MONEY, default=0)
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    fare_rules = models.TextField(blank=True)
    capacity = models.PositiveIntegerField()
    units_allocated = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["schedule", "cabin_class"], name="uniq_schedule_fare_class"),
            models.CheckConstraint(condition=Q(base_fare__gte=0), name="fare_base_non_negative"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="fare_tax_non_negative"),
            models.CheckConstraint(condition=Q(fee_amount__gte=0), name="fare_fee_non_negative"),
            models.CheckConstraint(condition=Q(units_allocated__lte=F("capacity")), name="fare_no_oversell"),
        ]

    @property
    def unit_total(self):
        return self.base_fare + self.tax_amount + self.fee_amount

    @property
    def available(self):
        return self.capacity - self.units_allocated

    def __str__(self):
        return f"{self.schedule} · {self.cabin_class.name}"


class InventoryHold(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONVERTED = "converted", "Converted to confirmed booking"
        RELEASED = "released", "Released"
        EXPIRED = "expired", "Expired"

    fare = models.ForeignKey(Fare, on_delete=models.PROTECT, related_name="holds")
    booking = models.OneToOneField("bookings.Booking", on_delete=models.CASCADE, related_name="hold")
    quantity = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="hold_quantity_positive")]

    def __str__(self):
        return f"{self.quantity} × {self.fare} ({self.status})"
