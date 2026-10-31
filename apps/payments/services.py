"""Payment lifecycle. A booking is confirmed only after the server has verified the payment with Razorpay
and its places are still held. The same code path runs for the checkout callback, webhooks and
reconciliation, and every step is safe to repeat."""

import hashlib
import json
import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import set_status
from apps.schedules.models import InventoryHold
from apps.support.notifications import notify
from apps.tickets import services as tickets

from . import gateway
from .models import GatewayEvent, PaymentTransaction, Refund

T = PaymentTransaction.Status


class PaymentError(Exception):
    pass


def dummy_mode():
    """True when PAYMENT_GATEWAY=dummy. Never true while live payments are on."""
    if settings.PAYMENTS_LIVE_MODE:
        return False
    name = getattr(settings, "PAYMENT_GATEWAY", None) or os.environ.get("PAYMENT_GATEWAY", "razorpay")
    return name.strip().lower() == "dummy"


def ensure_payable(booking):
    """Raises PaymentError unless the booking is unpaid and its places are still held."""
    if booking.status != Booking.Status.PENDING:
        raise PaymentError("This booking isn't waiting for payment.")
    hold = InventoryHold.objects.filter(booking=booking, status=InventoryHold.Status.ACTIVE).first()
    if not hold or hold.expires_at <= timezone.now():
        raise PaymentError("Your reservation has expired. Please book again.")


@transaction.atomic
def pay_dummy(booking):
    """Demo payment: no money moves. Marks the booking paid, confirms it and issues the tickets,
    through the same confirmation step real payments use."""
    if not dummy_mode():
        raise PaymentError("Dummy payments are switched off.")
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    ensure_payable(booking)
    txn = PaymentTransaction.objects.create(
        booking=booking, gateway="dummy", gateway_order_id=f"dummy_order_{uuid.uuid4().hex}",
        gateway_payment_id=f"dummy_pay_{uuid.uuid4().hex}", amount=booking.total_amount, currency=booking.currency,
        status=T.CAPTURED, is_live=False, signature_verified=True, captured_at=timezone.now(),
    )
    _confirm(txn)
    return txn


def start_payment(booking):
    """The gateway order to pay this booking, creating it on first use."""
    ensure_payable(booking)
    if not gateway.is_configured():
        raise PaymentError("Online payment isn't configured yet.")
    existing = booking.payments.filter(status=T.CREATED, amount=booking.total_amount).first()
    if existing:
        return existing
    order = gateway.create_order(booking.total_amount, booking.reference)
    return PaymentTransaction.objects.create(
        booking=booking, gateway="razorpay", gateway_order_id=order["id"], amount=booking.total_amount,
        currency=booking.currency, is_live=settings.PAYMENTS_LIVE_MODE,
    )


@transaction.atomic
def record_success(txn, payment_id, signature_verified=False):
    """Verify a payment with Razorpay's API, capture it if needed, then confirm the booking."""
    txn = PaymentTransaction.objects.select_for_update().get(pk=txn.pk)
    if txn.status == T.CAPTURED:
        return txn
    payment = gateway.fetch_payment(payment_id)
    expected = gateway.to_paise(txn.amount)
    if payment.get("order_id") != txn.gateway_order_id or payment.get("amount") != expected or payment.get("currency") != "INR":
        txn.failure_reason = "Payment details didn't match the order"
        txn.save(update_fields=["failure_reason", "updated_at"])
        raise PaymentError("The payment doesn't match this booking. Nothing has been confirmed; contact support.")
    if payment.get("status") == "authorized":
        payment = gateway.capture(payment_id, expected)
    if payment.get("status") != "captured":
        raise PaymentError("The payment hasn't completed yet.")

    txn.gateway_payment_id = payment_id
    txn.status = T.CAPTURED
    txn.captured_at = timezone.now()
    txn.signature_verified = txn.signature_verified or signature_verified
    txn.failure_reason = ""
    txn.save()
    _confirm(txn)
    return txn


def _confirm(txn):
    booking = Booking.objects.select_for_update().get(pk=txn.booking_id)
    if booking.status == Booking.Status.CONFIRMED:
        return
    hold = InventoryHold.objects.select_for_update().filter(booking=booking).first()
    if booking.status == Booking.Status.PENDING and hold and hold.status == InventoryHold.Status.ACTIVE:
        hold.status = InventoryHold.Status.CONVERTED
        hold.save(update_fields=["status", "updated_at"])
        booking.confirmed_at = timezone.now()
        booking.save(update_fields=["confirmed_at"])
        set_status(booking, Booking.Status.CONFIRMED, f"Payment {txn.gateway_payment_id} verified")
        tickets.issue(booking)
        notify("booking_confirmed", booking)
        return
    # ponytail: money arrived after the places were released; queue a full refund rather than re-taking places.
    if not txn.refunds.exists():
        queue_refund(txn, txn.amount, "Payment received after the reservation was released")
    set_status(booking, booking.status, f"Payment {txn.gateway_payment_id} received after release; refund queued")


def record_failure(txn, reason):
    updated = PaymentTransaction.objects.filter(pk=txn.pk, status=T.CREATED).update(
        status=T.FAILED, failure_reason=reason[:255], updated_at=timezone.now()
    )
    if updated and txn.booking.status == Booking.Status.PENDING:
        notify("payment_failed", txn.booking)
    return bool(updated)


@transaction.atomic
def queue_refund(txn, amount, reason, by=None, cancellation_request=None):
    """Create a pending refund, never more than what's left to refund on the payment."""
    txn = PaymentTransaction.objects.select_for_update().get(pk=txn.pk)
    if amount <= 0:
        return None
    if amount > txn.refundable_amount():
        raise PaymentError(f"Refund of ₹{amount} is more than the ₹{txn.refundable_amount()} left on this payment.")
    return Refund.objects.create(payment=txn, amount=amount, reason=reason[:255], initiated_by=by,
                                 cancellation_request=cancellation_request)


def send_refund(refund):
    """Ask Razorpay to pay a pending refund back to the original payment method."""
    R = Refund.Status
    claimed = Refund.objects.filter(pk=refund.pk, status__in=[R.PENDING, R.FAILED]).update(status=R.PROCESSING)
    if not claimed:
        return refund
    refund.refresh_from_db()
    if refund.payment.gateway == "dummy":  # nothing was really paid, so nothing to send back
        refund.gateway_refund_id = f"dummy_refund_{refund.pk}"
        refund.status = R.SUCCEEDED
        refund.save(update_fields=["gateway_refund_id", "status", "updated_at"])
        notify("refund_processed", refund.payment.booking, refund=refund)
        return refund
    try:
        result = gateway.refund(refund.payment.gateway_payment_id, gateway.to_paise(refund.amount), f"refund-{refund.pk}")
    except Exception as e:  # SDK raises several error types; all mean "not sent"
        refund.status, refund.failure_reason = R.FAILED, str(e)[:255]
        refund.save(update_fields=["status", "failure_reason", "updated_at"])
        notify("refund_failed", refund.payment.booking, refund=refund)
        return refund
    refund.gateway_refund_id = result.get("id")
    refund.status = R.SUCCEEDED if result.get("status") == "processed" else R.PROCESSING
    refund.save(update_fields=["gateway_refund_id", "status", "updated_at"])
    if refund.status == R.SUCCEEDED:
        notify("refund_processed", refund.payment.booking, refund=refund)
    return refund


def _refund_event(event_type, entity):
    refund = Refund.objects.filter(gateway_refund_id=entity.get("id")).first()
    if refund is None:
        return "unknown refund"
    if event_type == "refund.processed" and refund.status != Refund.Status.SUCCEEDED:
        refund.status = Refund.Status.SUCCEEDED
        refund.save(update_fields=["status", "updated_at"])
        notify("refund_processed", refund.payment.booking, refund=refund)
    elif event_type == "refund.failed" and refund.status != Refund.Status.FAILED:
        refund.status, refund.failure_reason = Refund.Status.FAILED, "Reported failed by Razorpay"
        refund.save(update_fields=["status", "failure_reason", "updated_at"])
        notify("refund_failed", refund.payment.booking, refund=refund)
    return event_type


def handle_webhook(body, signature, event_id):
    """Process one Razorpay webhook. Returns a short outcome string. Raises SignatureError if unsigned."""
    gateway.verify_webhook(body, signature)
    payload = json.loads(body)
    event, created = GatewayEvent.objects.get_or_create(
        gateway="razorpay",
        event_id=event_id or hashlib.sha256(body.encode()).hexdigest(),
        defaults={"event_type": payload.get("event", ""), "payload": payload, "signature_valid": True},
    )
    if not created and event.processed_at:
        return "duplicate"

    if event.event_type.startswith("refund."):
        outcome = _refund_event(event.event_type, payload.get("payload", {}).get("refund", {}).get("entity", {}))
        event.processed_at = timezone.now()
        event.save()
        return outcome

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    txn = PaymentTransaction.objects.filter(gateway_order_id=entity.get("order_id")).first()
    outcome = "ignored"
    try:
        if txn is None:
            outcome = "unknown order"
        elif event.event_type in ("payment.captured", "order.paid", "payment.authorized"):
            record_success(txn, entity["id"])
            outcome = "confirmed"
        elif event.event_type == "payment.failed":
            record_failure(txn, entity.get("error_description") or "Payment failed")
            outcome = "failed"
    except PaymentError as e:
        event.processing_error = str(e)
        outcome = "error"
    event.transaction = txn
    event.processed_at = timezone.now()
    event.save()
    return outcome


def reconcile(older_than_minutes=5):
    """Ask Razorpay about orders still marked 'created' and settle any that were actually paid."""
    settled = 0
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    for txn in PaymentTransaction.objects.filter(status=T.CREATED, created_at__lte=cutoff):
        paid = [p for p in gateway.order_payments(txn.gateway_order_id) if p.get("status") in ("captured", "authorized")]
        if paid:
            try:
                record_success(txn, paid[0]["id"])
                settled += 1
            except PaymentError:
                pass
    return settled
