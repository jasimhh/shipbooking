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
        """Sailings the public may view (not drafts or unapproved)."""
        return self.exclude(status__in=[Schedule.Status.DRAFT, Schedule.Status.PENDING_APPROVAL])

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
        PENDING_APPROVAL = "pending_approval", "Awaiting approval"
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

    EDITABLE = (Status.DRAFT, Status.PENDING_APPROVAL)
    LIVE = (Status.PUBLISHED, Status.DELAYED)

    @classmethod
    def from_db(cls, db, field_names, values):
        # Remember the stored status so a post_save handler can tell passengers about changes.
        instance = super().from_db(db, field_names, values)
        instance._loaded_status = instance.__dict__.get("status")
        return instance

    def clean(self):
        errors = {}
        if self.route_id and self.vessel_id and self.route.operator_id != self.vessel.operator_id:
            errors["vessel"] = "Vessel and route must belong to the same operator."
        if self.departure_at and self.arrival_at:
            if self.arrival_at <= self.departure_at:
                errors["arrival_at"] = "Arrival must be after departure."
            elif self.vessel_id:
                clash = (
                    Schedule.objects.filter(vessel_id=self.vessel_id)
                    .exclude(pk=self.pk)
                    .exclude(status=self.Status.CANCELLED)
                    .filter(departure_at__lt=self.arrival_at, arrival_at__gt=self.departure_at)
                    .first()
                )
                if clash:
                    errors["departure_at"] = f"{self.vessel} is already sailing at this time ({clash})."
        if self.booking_closes_at and self.departure_at and self.booking_closes_at > self.departure_at:
            errors["booking_closes_at"] = "Booking must close before departure."
        if self.pk and self.vessel_id and self.fares.exclude(cabin_class__vessel_id=self.vessel_id).exists():
            errors["vessel"] = "Remove this sailing's fares before changing the vessel."
        if errors:
            raise ValidationError(errors)

    def publish_problems(self):
        """Reasons this sailing can't go on sale yet; empty when it can."""
        problems = []
        if not self.fares.exists():
            problems.append("it has no fares")
        if self.departure_at <= timezone.now():
            problems.append("it has already departed")
        if self.route.operator.verification_status != Operator.Verification.VERIFIED:
            problems.append("its operator isn't verified")
        return problems

    @property
    def operator(self):
        return self.route.operator

    @property
    def duration(self):
        return self.arrival_at - self.departure_at

    def __str__(self):
        return f"{self.route} {timezone.localtime(self.departure_at):%Y-%m-%d %H:%M}"


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
    capacity = models.PositiveIntegerField(blank=True, help_text="Leave blank to use the cabin class capacity.")
    units_allocated = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["schedule", "cabin_class"], name="uniq_schedule_fare_class"),
            models.CheckConstraint(condition=Q(base_fare__gte=0), name="fare_base_non_negative"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="fare_tax_non_negative"),
            models.CheckConstraint(condition=Q(fee_amount__gte=0), name="fare_fee_non_negative"),
            models.CheckConstraint(condition=Q(units_allocated__lte=F("capacity")), name="fare_no_oversell"),
        ]

    def clean(self):
        if not self.cabin_class_id:
            return
        cabin = self.cabin_class
        # Inline forms attach a not-yet-saved schedule, so check the object rather than schedule_id.
        schedule = self.schedule if Fare.schedule.is_cached(self) or self.schedule_id else None
        if schedule and schedule.vessel_id and cabin.vessel_id != schedule.vessel_id:
            raise ValidationError({"cabin_class": "This cabin class belongs to a different vessel."})
        if self.capacity is None:
            self.capacity = cabin.capacity
        if self.capacity > cabin.capacity:
            raise ValidationError({"capacity": f"Can't exceed the cabin class capacity of {cabin.capacity}."})
        if self.capacity < self.units_allocated:
            raise ValidationError({"capacity": f"{self.units_allocated} places are already held or sold."})

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
