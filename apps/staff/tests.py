from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.tests import BookingSetup
from apps.compliance.models import AuditLog
from apps.fleet.models import CabinClass, Port, Route, Vessel
from apps.operators.models import Operator, OperatorMembership
from apps.payments import services as payments
from apps.payments.tests import KEYS, FakeRazorpay
from apps.schedules.models import Fare, Schedule
from apps.support.models import SupportMessage, SupportTicket

PASSWORD = "harbour-lights-42"


@override_settings(**KEYS)
class StaffAreaTest(BookingSetup, TestCase):
    """One paid booking (2 passengers, ₹860) on operator 'Op', plus a second operator with its own sailing."""

    def setUp(self):
        self.make()
        rzp = FakeRazorpay()
        for name in ["create_order", "fetch_payment", "capture"]:
            patcher = mock.patch(f"apps.payments.gateway.{name}", getattr(rzp, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.booking = self.reserve(2)
        txn = payments.start_payment(self.booking)
        payments.record_success(txn, rzp.pay(txn.gateway_order_id))

        self.op = self.schedule.route.operator
        other = Operator.objects.create(name="Other", verification_status=Operator.Verification.VERIFIED)
        vessel = Vessel.objects.create(operator=other, name="MV Other")
        cabin = CabinClass.objects.create(vessel=vessel, code="D", name="Deck", capacity=10)
        route = Route.objects.create(operator=other, origin=Port.objects.get(code="P1"), destination=Port.objects.get(code="P2"))
        dep = timezone.now() + timedelta(days=1)
        self.other_sailing = Schedule.objects.create(route=route, vessel=vessel, departure_at=dep, arrival_at=dep + timedelta(hours=1),
                                                     status=Schedule.Status.PUBLISHED)
        Fare.objects.create(schedule=self.other_sailing, cabin_class=cabin, base_fare=100, capacity=10)

        self.crew = User.objects.create_user("crew@op.example", PASSWORD, role=User.Role.OPERATOR)
        OperatorMembership.objects.create(operator=self.op, user=self.crew, can_view_manifests=True)
        self.support = User.objects.create_user("help@example.com", PASSWORD, role=User.Role.SUPPORT)
        self.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)

    def get(self, user, name, *args, **params):
        self.client.force_login(user)
        return self.client.get(reverse(f"staff:{name}", args=args), params)

    def test_passengers_cannot_enter(self):
        for name, args in [("dashboard", []), ("reports", []), ("support", []), ("manifest", [self.schedule.pk])]:
            self.assertEqual(self.get(self.user, name, *args).status_code, 403)

    def test_operator_dashboard_scoped_to_own_sailings(self):
        upcoming = list(self.get(self.crew, "dashboard").context["upcoming"])
        self.assertEqual([s.pk for s in upcoming], [self.schedule.pk])
        self.assertEqual((upcoming[0].sold, upcoming[0].capacity), (2, 4))
        admin_view = self.get(self.admin, "dashboard").context
        self.assertEqual(len(admin_view["upcoming"]), 2)
        self.assertEqual(admin_view["revenue_7d"], self.booking.total_amount)

    def test_manifest_access_content_and_audit(self):
        page = self.get(self.crew, "manifest", self.schedule.pk)
        self.assertEqual(len(page.context["rows"]), 2)
        self.assertEqual(page.context["rows"][0][-1], "Valid")
        self.assertEqual(self.get(self.crew, "manifest", self.other_sailing.pk).status_code, 403)
        csv_response = self.get(self.crew, "manifest", self.schedule.pk, format="csv")
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn("Passenger 0", csv_response.content.decode())
        self.assertEqual(AuditLog.objects.filter(action__startswith="manifest.").count(), 2)
        OperatorMembership.objects.filter(user=self.crew).update(can_view_manifests=False)
        self.assertEqual(self.get(self.crew, "manifest", self.schedule.pk).status_code, 403)

    def test_reports_scope_and_money_visibility(self):
        crew = self.get(self.crew, "reports").context
        self.assertEqual(crew["money"]["captured"], self.booking.total_amount)
        self.assertEqual([s.pk for s in crew["sailings"]], [self.schedule.pk])
        self.assertIsNone(self.get(self.support, "reports").context["money"])  # support sees no money
        # an operator can't widen the report to another operator via the filter
        bad = self.get(self.crew, "reports", start="2020-01-01", end="2030-01-01", operator=self.other_sailing.route.operator_id)
        self.assertIn("operator", bad.context["form"].errors)
        csv_response = self.get(self.admin, "reports", start=str(timezone.localdate()), end=str(timezone.localdate() + timedelta(days=5)), format="csv")
        self.assertIn("Occupancy %", csv_response.content.decode())

    def test_admin_passenger_list_searchable_and_audited(self):
        superuser = User.objects.create_superuser("root@example.com", PASSWORD)
        self.client.force_login(superuser)
        page = self.client.get(reverse("admin:bookings_bookingpassenger_changelist"), {"q": '"Passenger 1"'})
        self.assertContains(page, self.booking.reference)
        self.assertEqual(page.context["cl"].result_count, 1)
        self.assertTrue(AuditLog.objects.filter(action="passengers.listed").exists())

    def test_support_desk_is_support_and_admin_only(self):
        self.assertEqual(self.get(self.crew, "support").status_code, 403)
        self.assertEqual(self.get(self.support, "support").status_code, 200)


class SupportThreadTest(TestCase):
    def setUp(self):
        self.pax = User.objects.create_user("pax@example.com", PASSWORD, email_verified=True)
        self.stranger = User.objects.create_user("x@example.com", PASSWORD, email_verified=True)
        self.agent = User.objects.create_user("help@example.com", PASSWORD, role=User.Role.SUPPORT)
        self.ticket = SupportTicket.objects.create(user=self.pax, contact_email="pax@example.com", category="booking", subject="Seat question")
        SupportMessage.objects.create(ticket=self.ticket, author=self.pax, body="Can I change seats?")

    def test_staff_reply_emails_customer_and_customer_can_answer(self):
        self.client.force_login(self.agent)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("staff:support_detail", args=[self.ticket.reference]),
                             {"body": "Yes, at the port.", "status": "awaiting_customer"})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, SupportTicket.Status.AWAITING_CUSTOMER)
        self.assertEqual(mail.outbox[0].to, ["pax@example.com"])
        self.assertIn("Yes, at the port.", mail.outbox[0].body)

        self.client.force_login(self.pax)
        self.assertContains(self.client.get(reverse("support:ticket", args=[self.ticket.reference])), "Yes, at the port.")
        self.client.post(reverse("support:reply", args=[self.ticket.reference]), {"body": "Thanks!"})
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.messages.count()), (SupportTicket.Status.OPEN, 3))

    def test_tickets_are_private(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse("support:ticket", args=[self.ticket.reference])).status_code, 404)
        self.client.post(reverse("support:reply", args=[self.ticket.reference]), {"body": "hi"})
        self.assertEqual(self.ticket.messages.count(), 1)

    def test_guest_ticket_shows_up_after_verified_sign_in(self):
        guest = SupportTicket.objects.create(contact_email="PAX@example.com", category="other", subject="Before I registered")
        self.client.force_login(self.pax)
        self.assertIn(guest, self.client.get(reverse("support:mine")).context["tickets"])
