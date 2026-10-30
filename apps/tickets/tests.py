"""Phase 7: tickets, notifications, cancellations, refunds and sailing changes."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import cancellation
from apps.bookings.models import Booking, CancellationRequest, CancellationRule
from apps.bookings.tests import BookingSetup
from apps.compliance.models import PolicyVersion
from apps.operators.models import OperatorMembership
from apps.payments import services as payments
from apps.payments.models import Refund
from apps.payments.tests import KEYS, FakeRazorpay, sign
from apps.schedules.models import Schedule

from . import services
from .models import Ticket, TicketVerificationEvent

PASSWORD = "harbour-lights-42"


@override_settings(**KEYS)
class ConfirmedBookingCase(BookingSetup, TestCase):
    """A confirmed, paid booking for 2 passengers (₹860) on a sailing 2 days away."""

    def setUp(self):
        self.make()
        self.rzp = FakeRazorpay()
        self.rzp.refund = mock.Mock(return_value={"id": "rfnd_1", "status": "processed"})
        for name in ["create_order", "fetch_payment", "capture", "order_payments", "refund"]:
            patcher = mock.patch(f"apps.payments.gateway.{name}", getattr(self.rzp, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.booking = self.reserve(2)
            txn = payments.start_payment(self.booking)
            self.payment = payments.record_success(txn, self.rzp.pay(txn.gateway_order_id))
        self.booking.refresh_from_db()


class TicketTest(ConfirmedBookingCase):
    def test_confirmation_issues_ticket_and_emails(self):
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(self.booking.tickets.filter(status=Ticket.Status.VALID).count(), 1)
        subjects = [m.subject for m in mail.outbox]
        self.assertIn(f"Booking {self.booking.reference} confirmed", subjects)
        self.assertTrue(any(s.startswith("Reservation") for s in subjects))

    def test_pdf_download_owner_only(self):
        response = self.client.get(reverse("tickets:pdf", args=[self.booking.reference]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("tickets:pdf", args=[self.booking.reference])).status_code, 404)

    def test_qr_holds_only_a_verification_url(self):
        ticket = self.booking.tickets.get()
        url = services.verify_url(ticket)
        self.assertTrue(url.endswith(f"/tickets/verify/{ticket.verification_token}/"))
        self.assertNotIn("Passenger", url)

    def test_reissue_voids_old_ticket(self):
        old = self.booking.tickets.get()
        new = services.issue(self.booking)
        old.refresh_from_db()
        self.assertEqual(old.status, Ticket.Status.VOID)
        self.assertNotEqual(old.verification_token, new.verification_token)

    def test_staff_verification_and_boarding(self):
        ticket = self.booking.tickets.get()
        url = reverse("tickets:verify", args=[ticket.verification_token])
        self.assertEqual(self.client.get(url).status_code, 403)  # passengers can't scan tickets

        staff = User.objects.create_user("crew@op.example", PASSWORD, role=User.Role.OPERATOR)
        OperatorMembership.objects.create(operator=self.schedule.route.operator, user=staff, can_view_manifests=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).context["result"], "valid")
        self.client.post(reverse("tickets:board", args=[ticket.verification_token]))
        self.assertEqual(self.client.get(url).context["result"], "already_boarded")
        self.assertEqual(TicketVerificationEvent.objects.count(), 2)


class LookupTest(ConfirmedBookingCase):
    def test_lookup_needs_reference_and_email(self):
        self.client.logout()
        url = reverse("bookings:lookup")
        found = self.client.get(url, {"reference": self.booking.reference.lower(), "email": "PAX@example.com"})
        self.assertEqual(found.context["booking"], self.booking)
        self.assertNotContains(found, "Passenger 0")  # no names on the public page
        self.assertIsNone(self.client.get(url, {"reference": self.booking.reference, "email": "x@example.com"}).context["booking"])


class CancellationTest(ConfirmedBookingCase):
    def publish_policy(self):
        policy = PolicyVersion.objects.create(policy_type="cancellation", version="1", body="Terms",
                                              effective_from=timezone.now() - timedelta(days=1), is_published=True)
        CancellationRule.objects.create(policy=policy, min_hours_before_departure=24, refund_percent=75)
        CancellationRule.objects.create(policy=policy, min_hours_before_departure=0, refund_percent=0)
        return policy

    def test_quote_follows_published_rules_only(self):
        self.assertEqual(cancellation.quote(self.booking), (None, None, None))
        self.publish_policy()
        _, rule, amount = cancellation.quote(self.booking)
        self.assertEqual((rule.refund_percent, amount), (75, Decimal("645.00")))
        _, rule, amount = cancellation.quote(self.booking, now=self.schedule.departure_at - timedelta(hours=2))
        self.assertEqual(amount, Decimal("0.00"))

    def test_request_approve_releases_places_voids_ticket_and_refunds(self):
        self.publish_policy()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("bookings:request_cancel", args=[self.booking.reference]), {"reason": "Plans changed"})
        req = CancellationRequest.objects.get()
        self.assertEqual(req.eligible_refund_amount, Decimal("645.00"))
        admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)

        with self.captureOnCommitCallbacks(execute=True):
            refund = cancellation.approve(req, admin)
            payments.send_refund(refund)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(self.allocated(), 0)
        self.assertFalse(self.booking.tickets.filter(status=Ticket.Status.VALID).exists())
        refund.refresh_from_db()
        self.assertEqual((refund.status, refund.gateway_refund_id), (Refund.Status.SUCCEEDED, "rfnd_1"))
        self.rzp.refund.assert_called_once()
        self.assertIn(f"Refund for {self.booking.reference} sent", [m.subject for m in mail.outbox])
        with self.assertRaises(cancellation.CancellationError):
            cancellation.approve(req, admin)  # decided once

    def test_refunds_never_exceed_payment(self):
        with self.assertRaises(payments.PaymentError):
            payments.queue_refund(self.payment, self.payment.amount + 1, "too much")
        payments.queue_refund(self.payment, Decimal("800"), "partial")
        with self.assertRaises(payments.PaymentError):
            payments.queue_refund(self.payment, Decimal("100"), "over the rest")

    def test_reject_keeps_booking(self):
        req = cancellation.request_cancellation(self.booking, self.user, "Maybe")
        cancellation.reject(req, self.user, "Within no-refund window")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_refund_webhook_marks_processed(self):
        refund = payments.queue_refund(self.payment, Decimal("100"), "test")
        Refund.objects.filter(pk=refund.pk).update(status=Refund.Status.PROCESSING, gateway_refund_id="rfnd_9")
        body = '{"event": "refund.processed", "payload": {"refund": {"entity": {"id": "rfnd_9"}}}}'
        self.client.post(reverse("payments:razorpay_webhook"), body, content_type="application/json",
                         HTTP_X_RAZORPAY_SIGNATURE=sign(KEYS["RAZORPAY_WEBHOOK_SECRET"], body), HTTP_X_RAZORPAY_EVENT_ID="evt_r")
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.SUCCEEDED)


class SailingChangeTest(ConfirmedBookingCase):
    def test_operator_cancellation_cancels_bookings_and_queues_full_refunds(self):
        schedule = Schedule.objects.get(pk=self.schedule.pk)
        schedule.status = Schedule.Status.CANCELLED
        with self.captureOnCommitCallbacks(execute=True):
            schedule.save()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(Refund.objects.get().amount, self.booking.total_amount)
        self.assertIn(f"Your sailing {self.booking.reference} has been cancelled", [m.subject for m in mail.outbox])

    def test_delay_notifies_without_cancelling(self):
        schedule = Schedule.objects.get(pk=self.schedule.pk)
        schedule.status, schedule.status_note = Schedule.Status.DELAYED, "Fog"
        with self.captureOnCommitCallbacks(execute=True):
            schedule.save()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        delay = [m for m in mail.outbox if m.subject.startswith("Delay")]
        self.assertEqual(len(delay), 1)
        self.assertIn("Fog", delay[0].body)
