"""Checks that the database itself enforces the spec's hard rules."""

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.bookings.models import Booking, BookingSeat
from apps.compliance.models import AuditLog
from apps.fleet.models import CabinClass, Port, Route, Seat, Vessel
from apps.operators.models import Operator
from apps.payments.models import PaymentTransaction, Refund
from apps.schedules.models import Fare, Schedule


class SchemaRulesTest(TestCase):
    def setUp(self):
        self.op = Operator.objects.create(name="Demo Operator (fictional)", is_demo=True)
        self.a = Port.objects.create(code="AAA", name="Port A", city="A", state="S")
        self.b = Port.objects.create(code="BBB", name="Port B", city="B", state="S")
        self.route = Route.objects.create(operator=self.op, origin=self.a, destination=self.b)
        self.vessel = Vessel.objects.create(operator=self.op, name="Demo Vessel", seating_mode="assigned")
        self.cabin = CabinClass.objects.create(vessel=self.vessel, code="SEAT", name="Seater", capacity=2)
        self.dep = timezone.now() + timedelta(days=3)
        self.schedule = Schedule.objects.create(
            route=self.route, vessel=self.vessel, departure_at=self.dep, arrival_at=self.dep + timedelta(hours=4)
        )
        self.fare = Fare.objects.create(
            schedule=self.schedule, cabin_class=self.cabin, base_fare=Decimal("500.00"), capacity=2
        )

    def booking(self):
        return Booking.objects.create(
            schedule=self.schedule, fare=self.fare, contact_email="a@example.com", contact_phone="9000000000",
            passenger_count=1, base_amount=500, tax_amount=0, fee_amount=0, total_amount=500,
        )

    def assertRejected(self, fn):
        with self.assertRaises(IntegrityError), transaction.atomic():
            fn()

    def test_identical_ports_rejected(self):
        self.assertRejected(lambda: Route.objects.create(operator=self.op, origin=self.a, destination=self.a))

    def test_arrival_must_follow_departure(self):
        self.assertRejected(lambda: Schedule.objects.create(
            route=self.route, vessel=self.vessel, departure_at=self.dep, arrival_at=self.dep
        ))

    def test_negative_fare_rejected(self):
        other = CabinClass.objects.create(vessel=self.vessel, code="DECK", name="Deck", capacity=5)
        self.assertRejected(lambda: Fare.objects.create(
            schedule=self.schedule, cabin_class=other, base_fare=Decimal("-1"), capacity=5
        ))

    def test_cannot_oversell(self):
        self.fare.units_allocated = 2
        self.fare.save()
        self.fare.units_allocated = 3
        self.assertRejected(self.fare.save)

    def test_zero_passengers_rejected(self):
        self.assertRejected(lambda: Booking.objects.create(
            schedule=self.schedule, fare=self.fare, contact_email="a@example.com", contact_phone="1",
            passenger_count=0, base_amount=0, tax_amount=0, fee_amount=0, total_amount=0,
        ))

    def test_booking_references_unique_and_readable(self):
        refs = {self.booking().reference for _ in range(20)}
        self.assertEqual(len(refs), 20)
        self.assertTrue(all(r.startswith("SB") and len(r) == 10 for r in refs))

    def test_seat_cannot_be_double_allocated_until_released(self):
        seat = Seat.objects.create(cabin_class=self.cabin, number="1A")
        first = BookingSeat.objects.create(
            booking=self.booking(), schedule=self.schedule, seat=seat, active_schedule=self.schedule
        )
        second = self.booking()
        self.assertRejected(lambda: BookingSeat.objects.create(
            booking=second, schedule=self.schedule, seat=seat, active_schedule=self.schedule
        ))
        first.release()
        BookingSeat.objects.create(booking=second, schedule=self.schedule, seat=seat, active_schedule=self.schedule)

    def test_refundable_amount_never_exceeds_captured(self):
        pay = PaymentTransaction.objects.create(
            booking=self.booking(), gateway_order_id="order_test_1", amount=500, status="captured"
        )
        Refund.objects.create(payment=pay, amount=300)
        Refund.objects.create(payment=pay, amount=100, status="failed")
        self.assertEqual(pay.refundable_amount(), 200)
        pay.status = "failed"
        self.assertEqual(pay.refundable_amount(), 0)

    def test_audit_log_is_append_only(self):
        entry = AuditLog.objects.create(action="test", object_type="x", object_id="1")
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()
