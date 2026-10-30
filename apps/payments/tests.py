"""Payment tests against a simulated Razorpay. Network calls are faked; signature checks use the real SDK."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import expire_holds
from apps.bookings.tests import BookingSetup
from apps.schedules.models import InventoryHold

from . import services
from .models import GatewayEvent, PaymentTransaction, Refund

KEYS = {"RAZORPAY_KEY_ID": "rzp_test_dummy", "RAZORPAY_KEY_SECRET": "test-secret", "RAZORPAY_WEBHOOK_SECRET": "hook-secret"}


def sign(secret, message):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class FakeRazorpay:
    """Stands in for Razorpay's API: orders and payments kept in memory."""

    def __init__(self):
        self.orders, self.payments, self.n = {}, {}, 0

    def create_order(self, amount, receipt):
        self.n += 1
        order = {"id": f"order_test{self.n}", "amount": int(amount * 100), "currency": "INR", "receipt": receipt}
        self.orders[order["id"]] = order
        return order

    def pay(self, order_id, status="captured", amount=None):
        pid = f"pay_test{len(self.payments) + 1}"
        self.payments[pid] = {"id": pid, "order_id": order_id, "status": status, "currency": "INR",
                              "amount": amount if amount is not None else self.orders[order_id]["amount"]}
        return pid

    def fetch_payment(self, pid):
        return dict(self.payments[pid])

    def capture(self, pid, amount):
        self.payments[pid]["status"] = "captured"
        return dict(self.payments[pid])

    def order_payments(self, order_id):
        return [p for p in self.payments.values() if p["order_id"] == order_id]


@override_settings(**KEYS)
class PaymentTest(BookingSetup, TestCase):
    def setUp(self):
        self.make()
        self.rzp = FakeRazorpay()
        for name in ["create_order", "fetch_payment", "capture", "order_payments"]:
            patcher = mock.patch(f"apps.payments.gateway.{name}", getattr(self.rzp, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client.force_login(self.user)
        self.booking = self.reserve(2)

    def open_checkout(self):
        response = self.client.get(reverse("payments:pay", args=[self.booking.reference]))
        self.assertEqual(response.status_code, 200)
        return response.context["checkout"]

    def checkout_return(self, order_id, pid, signature=None):
        return self.client.post(reverse("payments:return", args=[self.booking.reference]), {
            "razorpay_order_id": order_id, "razorpay_payment_id": pid,
            "razorpay_signature": signature or sign(KEYS["RAZORPAY_KEY_SECRET"], f"{order_id}|{pid}"),
        })

    def webhook(self, event, pid, order_id, event_id="evt_1", secret=KEYS["RAZORPAY_WEBHOOK_SECRET"]):
        body = json.dumps({"event": event, "payload": {"payment": {"entity": {"id": pid, "order_id": order_id}}}})
        return self.client.post(reverse("payments:razorpay_webhook"), body, content_type="application/json",
                                HTTP_X_RAZORPAY_SIGNATURE=sign(secret, body), HTTP_X_RAZORPAY_EVENT_ID=event_id)

    def status(self):
        self.booking.refresh_from_db()
        return self.booking.status

    def test_order_amount_in_paise_and_reused_on_reload(self):
        checkout = self.open_checkout()
        self.assertEqual(checkout["amount"], 86000)  # ₹860.00
        self.assertEqual(self.open_checkout()["order_id"], checkout["order_id"])
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_verified_payment_confirms_booking_and_keeps_places(self):
        order = self.open_checkout()["order_id"]
        response = self.checkout_return(order, self.rzp.pay(order))
        self.assertRedirects(response, reverse("bookings:detail", args=[self.booking.reference]))
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)
        self.assertEqual(self.booking.hold.status, InventoryHold.Status.CONVERTED)
        self.assertEqual(self.allocated(), 2)
        txn = PaymentTransaction.objects.get()
        self.assertTrue(txn.signature_verified)
        # A confirmed booking's hold is never expired later.
        expire_holds(now=timezone.now() + timedelta(hours=1))
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_forged_signature_confirms_nothing(self):
        order = self.open_checkout()["order_id"]
        self.checkout_return(order, self.rzp.pay(order), signature="forged")
        self.assertEqual(self.status(), Booking.Status.PENDING)
        self.assertEqual(PaymentTransaction.objects.get().status, PaymentTransaction.Status.CREATED)

    def test_underpayment_rejected(self):
        order = self.open_checkout()["order_id"]
        self.checkout_return(order, self.rzp.pay(order, amount=100))
        self.assertEqual(self.status(), Booking.Status.PENDING)

    def test_authorized_payment_is_captured(self):
        order = self.open_checkout()["order_id"]
        pid = self.rzp.pay(order, status="authorized")
        self.checkout_return(order, pid)
        self.assertEqual(self.rzp.payments[pid]["status"], "captured")
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_webhook_confirms_once_and_ignores_duplicates(self):
        order = self.open_checkout()["order_id"]
        pid = self.rzp.pay(order)
        self.assertEqual(self.webhook("payment.captured", pid, order).content, b"confirmed")
        self.assertEqual(self.webhook("payment.captured", pid, order).content, b"duplicate")
        self.assertEqual(self.webhook("order.paid", pid, order, event_id="evt_2").content, b"confirmed")  # still idempotent
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)
        self.assertEqual(self.booking.status_history.filter(to_status="confirmed").count(), 1)
        self.assertEqual(GatewayEvent.objects.count(), 2)

    def test_webhook_with_bad_signature_rejected(self):
        order = self.open_checkout()["order_id"]
        response = self.webhook("payment.captured", self.rzp.pay(order), order, secret="wrong")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.status(), Booking.Status.PENDING)
        self.assertFalse(GatewayEvent.objects.exists())

    def test_failed_payment_allows_retry_with_new_order(self):
        order = self.open_checkout()["order_id"]
        self.webhook("payment.failed", self.rzp.pay(order, status="failed"), order)
        self.assertEqual(PaymentTransaction.objects.get().status, PaymentTransaction.Status.FAILED)
        self.assertEqual(self.status(), Booking.Status.PENDING)
        self.assertNotEqual(self.open_checkout()["order_id"], order)

    def test_payment_after_hold_released_queues_refund(self):
        order = self.open_checkout()["order_id"]
        expire_holds(now=timezone.now() + timedelta(minutes=16))
        self.checkout_return(order, self.rzp.pay(order))
        self.assertEqual(self.status(), Booking.Status.EXPIRED)
        refund = Refund.objects.get()
        self.assertEqual(refund.amount, self.booking.total_amount)
        self.assertEqual(self.allocated(), 0)

    def test_reconcile_settles_lost_callbacks(self):
        order = self.open_checkout()["order_id"]
        self.rzp.pay(order)  # paid, but neither callback nor webhook arrived
        self.assertEqual(services.reconcile(older_than_minutes=0), 1)
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_cannot_pay_someone_elses_booking(self):
        other = self.reserve(1, user=self.other)
        self.assertEqual(self.client.get(reverse("payments:pay", args=[other.reference])).status_code, 404)

    def test_expired_booking_cannot_start_payment(self):
        expire_holds(now=timezone.now() + timedelta(minutes=16))
        response = self.client.get(reverse("payments:pay", args=[self.booking.reference]))
        self.assertRedirects(response, reverse("bookings:detail", args=[self.booking.reference]))
        self.assertFalse(PaymentTransaction.objects.exists())


class NotConfiguredTest(BookingSetup, TestCase):
    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_pay_page_explains_missing_keys(self):
        self.make()
        self.client.force_login(self.user)
        booking = self.reserve(1)
        response = self.client.get(reverse("payments:pay", args=[booking.reference]))
        self.assertContains(response, "Payment isn't set up yet")
