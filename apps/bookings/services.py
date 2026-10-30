"""Reserving and releasing places. All inventory changes go through here.

Overselling is prevented by a conditional UPDATE (only succeeds while enough places
remain) inside a transaction, backed by the fare_no_oversell check constraint and,
for assigned seating, the uniq_active_seat constraint.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.fleet.models import Seat, Vessel
from apps.schedules.models import Fare, InventoryHold, Schedule
from apps.support.notifications import notify

from .models import Booking, BookingPassenger, BookingSeat, BookingStatusHistory

MAX_PENDING_PER_USER = 3


class BookingError(Exception):
    pass


def set_status(booking, status, note="", by=None):
    BookingStatusHistory.objects.create(booking=booking, from_status=booking.status, to_status=status, changed_by=by, note=note)
    booking.status = status
    booking.save(update_fields=["status", "updated_at"])


def price(fare, passenger_count):
    n = Decimal(passenger_count)
    return {
        "base_amount": fare.base_fare * n,
        "tax_amount": fare.tax_amount * n,
        "fee_amount": fare.fee_amount * n,
        "total_amount": fare.unit_total * n,
    }


@transaction.atomic
def reserve(user, fare_id, passengers, contact_email, contact_phone):
    """Create a pending booking and hold its places. Prices come from the database, never the client."""
    n = len(passengers)
    if not 1 <= n <= 9:
        raise BookingError("Choose between 1 and 9 passengers.")
    fare = Fare.objects.select_related("schedule__route__operator", "schedule__vessel", "cabin_class").get(pk=fare_id)
    schedule = fare.schedule
    if not Schedule.objects.bookable().filter(pk=schedule.pk).exists():
        raise BookingError("This sailing is no longer open for booking.")
    if schedule.route.operator.is_demo and settings.PAYMENTS_LIVE_MODE:
        raise BookingError("Demo sailings can't be booked while live payments are switched on.")
    if Booking.objects.filter(user=user, status=Booking.Status.PENDING).count() >= MAX_PENDING_PER_USER:
        raise BookingError(f"You already have {MAX_PENDING_PER_USER} unpaid reservations. Pay for or cancel one first.")

    taken = Fare.objects.filter(pk=fare.pk, units_allocated__lte=F("capacity") - n).update(units_allocated=F("units_allocated") + n)
    if not taken:
        raise BookingError("Sorry, there aren't enough places left in this class for your group.")

    amounts = price(fare, n)
    booking = Booking.objects.create(
        user=user, schedule=schedule, fare=fare, contact_email=contact_email, contact_phone=contact_phone,
        passenger_count=n, currency=fare.currency, **amounts,
        fare_snapshot={
            "cabin_class": fare.cabin_class.name, "base_fare": str(fare.base_fare), "tax_amount": str(fare.tax_amount),
            "fee_amount": str(fare.fee_amount), "unit_total": str(fare.unit_total), "fare_rules": fare.fare_rules,
        },
    )
    BookingStatusHistory.objects.create(booking=booking, to_status=booking.status, changed_by=user, note="Places reserved")
    rows = BookingPassenger.objects.bulk_create(BookingPassenger(booking=booking, **p) for p in passengers)
    InventoryHold.objects.create(
        fare=fare, booking=booking, quantity=n,
        expires_at=timezone.now() + timedelta(minutes=settings.INVENTORY_HOLD_MINUTES),
    )

    if schedule.vessel.seating_mode == Vessel.SeatingMode.ASSIGNED:
        # ponytail: seats are assigned automatically, lowest number first; add a seat picker if passengers ask for it.
        free = list(
            Seat.objects.filter(cabin_class=fare.cabin_class, is_active=True)
            .exclude(allocations__active_schedule=schedule).order_by("number")[:n]
        )
        if len(free) < n:
            raise BookingError("Sorry, there aren't enough seats left in this class for your group.")
        try:
            with transaction.atomic():
                BookingSeat.objects.bulk_create(
                    BookingSeat(booking=booking, passenger=p, schedule=schedule, seat=s, active_schedule=schedule)
                    for p, s in zip(rows, free)
                )
        except IntegrityError:
            raise BookingError("Those seats were just taken. Please try again.")
    notify("booking_reserved", booking)
    return booking


@transaction.atomic
def release(booking, status, note, by=None):
    """Give a pending booking's places back. Returns False if nothing was held."""
    hold = InventoryHold.objects.select_for_update().filter(booking=booking, status=InventoryHold.Status.ACTIVE).first()
    if hold is None:
        return False
    Fare.objects.filter(pk=hold.fare_id).update(units_allocated=F("units_allocated") - hold.quantity)
    hold.status = InventoryHold.Status.EXPIRED if status == Booking.Status.EXPIRED else InventoryHold.Status.RELEASED
    hold.save(update_fields=["status", "updated_at"])
    BookingSeat.objects.filter(booking=booking).update(active_schedule=None)
    set_status(booking, status, note, by)
    return True


def expire_holds(now=None):
    """Release every hold past its expiry. Cheap enough to call on each booking or search page."""
    due = InventoryHold.objects.filter(status=InventoryHold.Status.ACTIVE, expires_at__lte=now or timezone.now())
    count = 0
    for hold in due.select_related("booking"):
        count += release(hold.booking, Booking.Status.EXPIRED, "Hold expired before payment")
    return count
