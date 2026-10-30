"""Payment lifecycle. A booking is confirmed only after the server has verified the payment with Razorpay
and its places are still held. The same code path runs for the checkout callback, webhooks and
reconciliation, and every step is safe to repeat."""

import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import set_status
from apps.schedules.models import InventoryHold

from . import gateway
from .models import GatewayEvent, PaymentTransaction, Refund

T = PaymentTransaction.Status


class PaymentError(Exception):
    pass


def start_payment(booking):
    """The gateway order to pay this booking, creating it on first use."""
    if booking.status != Booking.Status.PENDING:
        raise PaymentError("This booking isn't waiting for payment.")
    hold = InventoryHold.objects.filter(booking=booking, status=InventoryHold.Status.ACTIVE).first()
    if not hold or hold.expires_at <= timezone.now():
        raise PaymentError("Your reservation has expired. Please book again.")
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
        return
    # ponytail: money arrived after the places were released; queue a full refund rather than re-taking places.
    if not txn.refunds.exists():
        Refund.objects.create(payment=txn, amount=txn.amount, reason="Payment received after the reservation was released")
    set_status(booking, booking.status, f"Payment {txn.gateway_payment_id} received after release; refund queued")


def record_failure(txn, reason):
    updated = PaymentTransaction.objects.filter(pk=txn.pk, status=T.CREATED).update(
        status=T.FAILED, failure_reason=reason[:255], updated_at=timezone.now()
    )
    return bool(updated)


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
