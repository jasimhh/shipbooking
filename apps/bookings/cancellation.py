"""Cancelling confirmed bookings. Refund amounts come only from the published, approved cancellation
policy's rules; with no published rules the request goes to an admin, who decides the amount."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.compliance.models import PolicyVersion
from apps.payments import services as payments
from apps.payments.models import PaymentTransaction
from apps.schedules.models import Fare, Schedule
from apps.support.notifications import notify
from apps.tickets import services as tickets

from .models import Booking, BookingSeat, CancellationRequest
from .services import set_status


class CancellationError(Exception):
    pass


def current_policy():
    return (PolicyVersion.objects.filter(policy_type="cancellation", is_published=True, effective_from__lte=timezone.now())
            .order_by("-effective_from").first())


def quote(booking, now=None):
    """(policy, rule, refund amount) for cancelling now. Rule and amount are None when no rule applies."""
    policy = current_policy()
    if policy is None or not policy.cancellation_rules.exists():
        return policy, None, None
    hours_left = (booking.schedule.departure_at - (now or timezone.now())).total_seconds() / 3600
    rule = policy.cancellation_rules.filter(min_hours_before_departure__lte=max(hours_left, 0)).first()
    if rule is None:
        return policy, None, Decimal("0.00")
    amount = (booking.total_amount * rule.refund_percent / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return policy, rule, amount


def can_request(booking):
    return (booking.status == Booking.Status.CONFIRMED
            and booking.schedule.departure_at > timezone.now()
            and not booking.cancellation_requests.filter(status=CancellationRequest.Status.REQUESTED).exists())


@transaction.atomic
def request_cancellation(booking, user, reason):
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if not can_request(booking):
        raise CancellationError("This booking can't be cancelled online. Contact support.")
    policy, _, amount = quote(booking)
    req = CancellationRequest.objects.create(
        booking=booking, requested_by=user, reason=reason, policy_version=policy, eligible_refund_amount=amount or 0,
    )
    notify("cancellation_requested", booking)
    return req


def _release_confirmed(booking):
    """Give a confirmed booking's places back to the sailing."""
    Fare.objects.filter(pk=booking.fare_id).update(units_allocated=F("units_allocated") - booking.passenger_count)
    BookingSeat.objects.filter(booking=booking).update(active_schedule=None)
    tickets.void_all(booking)


def _captured_payment(booking):
    return booking.payments.filter(status=PaymentTransaction.Status.CAPTURED).first()


@transaction.atomic
def approve(req, by, refund_amount=None):
    """Cancel the booking, release its places and queue the refund (policy amount unless an admin overrides)."""
    req = CancellationRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != CancellationRequest.Status.REQUESTED:
        raise CancellationError("This request has already been decided.")
    booking = Booking.objects.select_for_update().get(pk=req.booking_id)
    amount = req.eligible_refund_amount if refund_amount is None else Decimal(refund_amount)
    refund = None
    if amount > 0:
        payment = _captured_payment(booking)
        if payment is None:
            raise CancellationError("No captured payment to refund.")
        refund = payments.queue_refund(payment, amount, "Cancellation approved", by=by, cancellation_request=req)
    req.status, req.decided_by, req.decided_at = CancellationRequest.Status.APPROVED, by, timezone.now()
    req.eligible_refund_amount = amount
    req.save()
    if booking.status == Booking.Status.CONFIRMED:
        _release_confirmed(booking)
        set_status(booking, Booking.Status.CANCELLED, "Cancellation approved", by)
    notify("cancellation_approved", booking, refund=refund)
    return refund


@transaction.atomic
def reject(req, by, note):
    updated = CancellationRequest.objects.filter(pk=req.pk, status=CancellationRequest.Status.REQUESTED).update(
        status=CancellationRequest.Status.REJECTED, decided_by=by, decided_at=timezone.now(), decision_note=note,
    )
    if updated:
        notify("cancellation_rejected", req.booking, note=note)
    return bool(updated)


@transaction.atomic
def sailing_cancelled(schedule):
    """The operator cancelled the sailing: cancel every confirmed booking and queue full refunds."""
    for booking in Booking.objects.select_for_update().filter(schedule=schedule, status=Booking.Status.CONFIRMED):
        _release_confirmed(booking)
        set_status(booking, Booking.Status.CANCELLED, "Sailing cancelled by operator")
        payment = _captured_payment(booking)
        if payment and payment.refundable_amount() > 0:
            payments.queue_refund(payment, payment.refundable_amount(), "Sailing cancelled by operator")
        notify("sailing_cancelled", booking)


def sailing_delayed(schedule):
    for booking in Booking.objects.filter(schedule=schedule, status=Booking.Status.CONFIRMED):
        notify("sailing_delayed", booking)


def on_schedule_status_change(schedule, old_status):
    if schedule.status == old_status:
        return
    if schedule.status == Schedule.Status.CANCELLED:
        sailing_cancelled(schedule)
    elif schedule.status == Schedule.Status.DELAYED:
        sailing_delayed(schedule)
