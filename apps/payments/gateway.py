"""Thin wrapper over the official Razorpay SDK. Card, UPI and bank details never reach this server."""

from decimal import Decimal

import razorpay
from django.conf import settings

SignatureError = razorpay.errors.SignatureVerificationError


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_order(amount, receipt):
    return client().order.create({"amount": to_paise(amount), "currency": "INR", "receipt": receipt, "notes": {"booking": receipt}})


def fetch_payment(payment_id):
    return client().payment.fetch(payment_id)


def capture(payment_id, amount_paise):
    return client().payment.capture(payment_id, amount_paise, {"currency": "INR"})


def order_payments(order_id):
    return client().order.payments(order_id).get("items", [])


def verify_checkout(order_id, payment_id, signature):
    """Raises SignatureError unless Razorpay signed this order/payment pair with our key secret."""
    client().utility.verify_payment_signature({
        "razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
    })


def verify_webhook(body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise SignatureError("Webhook secret not configured")
    client().utility.verify_webhook_signature(body, signature, settings.RAZORPAY_WEBHOOK_SECRET)
