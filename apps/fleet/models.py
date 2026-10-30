from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.common import TimeStampedModel
from apps.operators.models import Operator


class Port(TimeStampedModel):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    boarding_instructions = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(latitude__gte=-90, latitude__lte=90) | Q(latitude__isnull=True), name="port_latitude_range"),
            models.CheckConstraint(condition=Q(longitude__gte=-180, longitude__lte=180) | Q(longitude__isnull=True), name="port_longitude_range"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Route(TimeStampedModel):
    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name="routes")
    origin = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="departing_routes")
    destination = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="arriving_routes")
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(origin=F("destination")), name="route_ports_differ"),
            models.UniqueConstraint(fields=["operator", "origin", "destination"], name="uniq_operator_route"),
        ]

    def clean(self):
        if self.origin_id and self.origin_id == self.destination_id:
            raise ValidationError({"destination": "Destination must be different from the origin."})

    def __str__(self):
        return f"{self.origin.code} → {self.destination.code}"


class Vessel(TimeStampedModel):
    class SeatingMode(models.TextChoices):
        CAPACITY = "capacity", "Capacity-based (no seat numbers)"
        ASSIGNED = "assigned", "Assigned seats"

    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name="vessels")
    name = models.CharField(max_length=150)
    imo_number = models.CharField("IMO number", max_length=20, unique=True, null=True, blank=True)
    vessel_type = models.CharField(max_length=50, blank=True)
    facilities = models.TextField(blank=True)
    seating_mode = models.CharField(max_length=20, choices=SeatingMode.choices, default=SeatingMode.CAPACITY)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CabinClass(TimeStampedModel):
    """A bookable class of space on a vessel (e.g. deck, seater, cabin) and its capacity."""

    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, related_name="cabin_classes")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    class Meta:
        verbose_name_plural = "cabin classes"
        constraints = [
            models.UniqueConstraint(fields=["vessel", "code"], name="uniq_vessel_cabin_class"),
            models.CheckConstraint(condition=Q(capacity__gt=0), name="cabin_capacity_positive"),
        ]

    def __str__(self):
        return f"{self.vessel} · {self.name}"


class Seat(models.Model):
    """Only used when the vessel's seating_mode is ASSIGNED."""

    cabin_class = models.ForeignKey(CabinClass, on_delete=models.CASCADE, related_name="seats")
    number = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cabin_class", "number"], name="uniq_seat_number")]

    def __str__(self):
        return f"{self.cabin_class} · {self.number}"
