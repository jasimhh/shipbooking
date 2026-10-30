from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.fleet.models import CabinClass, Port, Route, Seat, Vessel
from apps.operators.models import Operator
from apps.schedules.models import Fare, InventoryHold, Schedule

from . import services
from .models import Booking, BookingSeat

PASSWORD = "harbour-lights-42"


def people(n):
    return [{"full_name": f"Passenger {i}", "age": 30, "gender": "undisclosed"} for i in range(n)]


class BookingSetup:
    def make(self, seating="capacity", capacity=4):
        op = Operator.objects.create(name="Op", verification_status=Operator.Verification.VERIFIED)
        p1 = Port.objects.create(code="P1", name="Port One", city="x", state="y")
        p2 = Port.objects.create(code="P2", name="Port Two", city="x", state="y")
        route = Route.objects.create(operator=op, origin=p1, destination=p2)
        self.vessel = Vessel.objects.create(operator=op, name="MV Test", seating_mode=seating)
        self.cabin = CabinClass.objects.create(vessel=self.vessel, code="C", name="Cabin", capacity=capacity)
        if seating == "assigned":
            Seat.objects.bulk_create(Seat(cabin_class=self.cabin, number=f"{n:02d}") for n in range(1, capacity + 1))
        dep = timezone.now() + timedelta(days=2)
        self.schedule = Schedule.objects.create(route=route, vessel=self.vessel, departure_at=dep,
                                                arrival_at=dep + timedelta(hours=1), status=Schedule.Status.PUBLISHED)
        self.fare = Fare.objects.create(schedule=self.schedule, cabin_class=self.cabin, base_fare=Decimal("400"),
                                        tax_amount=Decimal("20"), fee_amount=Decimal("10"), capacity=capacity)
        self.user = User.objects.create_user("pax@example.com", PASSWORD, email_verified=True, first_name="Asha")
        self.other = User.objects.create_user("other@example.com", PASSWORD, email_verified=True)

    def reserve(self, n, user=None):
        return services.reserve(user or self.user, self.fare.pk, people(n), "pax@example.com", "+91 98000 00000")

    def allocated(self):
        self.fare.refresh_from_db()
        return self.fare.units_allocated


class ReservationTest(BookingSetup, TestCase):
    def setUp(self):
        self.make()

    def test_reserve_holds_places_and_prices_from_database(self):
        booking = self.reserve(3)
        self.assertEqual(self.allocated(), 3)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.total_amount, Decimal("1290.00"))  # (400 + 20 + 10) × 3
        self.assertEqual(booking.passengers.count(), 3)
        self.assertEqual(booking.hold.quantity, 3)
        self.assertEqual(booking.status_history.count(), 1)

    def test_cannot_oversell(self):
        self.reserve(3)
        with self.assertRaises(services.BookingError):
            self.reserve(2, user=self.other)
        self.assertEqual(self.allocated(), 3)
        self.reserve(1, user=self.other)
        self.assertEqual(self.allocated(), 4)
        with self.assertRaises(services.BookingError):
            self.reserve(1, user=self.other)

    def test_expired_hold_releases_places(self):
        booking = self.reserve(4)
        self.assertEqual(services.expire_holds(), 0)
        self.assertEqual(services.expire_holds(now=timezone.now() + timedelta(minutes=16)), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.EXPIRED)
        self.assertEqual(booking.hold.status, InventoryHold.Status.EXPIRED)
        self.assertEqual(self.allocated(), 0)
        self.assertEqual(services.expire_holds(now=timezone.now() + timedelta(hours=1)), 0)  # releases once

    def test_cancel_releases_once(self):
        booking = self.reserve(2)
        self.assertTrue(services.release(booking, Booking.Status.CANCELLED, "test"))
        self.assertFalse(services.release(booking, Booking.Status.CANCELLED, "again"))
        self.assertEqual(self.allocated(), 0)

    def test_unbookable_sailings_refused(self):
        for status in [Schedule.Status.DRAFT, Schedule.Status.PENDING_APPROVAL, Schedule.Status.CANCELLED]:
            Schedule.objects.filter(pk=self.schedule.pk).update(status=status)
            with self.assertRaises(services.BookingError):
                self.reserve(1)
        self.assertEqual(self.allocated(), 0)

    def test_pending_reservations_are_capped(self):
        Fare.objects.filter(pk=self.fare.pk).update(capacity=50)
        CabinClass.objects.filter(pk=self.cabin.pk).update(capacity=50)
        for _ in range(services.MAX_PENDING_PER_USER):
            self.reserve(1)
        with self.assertRaises(services.BookingError):
            self.reserve(1)

    @override_settings(PAYMENTS_LIVE_MODE=True)
    def test_demo_sailings_blocked_in_live_mode(self):
        Operator.objects.update(is_demo=True)
        with self.assertRaises(services.BookingError):
            self.reserve(1)


class AssignedSeatTest(BookingSetup, TestCase):
    def setUp(self):
        self.make(seating="assigned", capacity=3)

    def test_seats_assigned_uniquely_and_freed_on_release(self):
        first = self.reserve(2)
        second = self.reserve(1, user=self.other)
        taken = list(BookingSeat.objects.filter(active_schedule=self.schedule).values_list("seat__number", flat=True))
        self.assertEqual(sorted(taken), ["01", "02", "03"])
        services.release(first, Booking.Status.CANCELLED, "test")
        self.assertEqual(BookingSeat.objects.filter(active_schedule=self.schedule).count(), 1)
        third = self.reserve(2)
        self.assertEqual(sorted(third.seats.values_list("seat__number", flat=True)), ["01", "02"])
        self.assertEqual(second.seats.get().seat.number, "03")


class BookingPagesTest(BookingSetup, TestCase):
    def setUp(self):
        self.make()
        self.client.force_login(self.user)

    def post_details(self, n=2, **extra):
        data = {"fare": self.fare.pk, "contact_email": "pax@example.com", "contact_phone": "+91 98000 00000",
                "p-TOTAL_FORMS": n, "p-INITIAL_FORMS": 0, "p-MIN_NUM_FORMS": 1, "p-MAX_NUM_FORMS": 9}
        for i in range(n):
            data.update({f"p-{i}-full_name": f"P{i}", f"p-{i}-age": 30, f"p-{i}-gender": "female"})
        data.update(extra)
        return self.client.post(reverse("bookings:details", args=[self.schedule.pk]), data)

    def test_full_flow_details_review_reserve(self):
        self.assertRedirects(self.post_details(2), reverse("bookings:review", args=[self.schedule.pk]))
        review = self.client.get(reverse("bookings:review", args=[self.schedule.pk]))
        self.assertEqual(review.context["amounts"]["total_amount"], Decimal("860.00"))
        response = self.client.post(reverse("bookings:review", args=[self.schedule.pk]), {"total_amount": "1"})
        booking = Booking.objects.get()
        self.assertRedirects(response, reverse("bookings:detail", args=[booking.reference]))
        self.assertEqual(booking.total_amount, Decimal("860.00"))  # client-sent totals are ignored
        self.assertContains(self.client.get(reverse("accounts:dashboard")), booking.reference)

    def test_more_passengers_than_places_rejected_at_details(self):
        response = self.post_details(5)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["trip"].errors or response.context["people"].non_form_errors())

    def test_unverified_email_must_confirm_first(self):
        User.objects.filter(pk=self.user.pk).update(email_verified=False)
        response = self.client.get(reverse("bookings:details", args=[self.schedule.pk]))
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_bookings_are_private(self):
        booking = self.reserve(1, user=self.other)
        self.assertEqual(self.client.get(reverse("bookings:detail", args=[booking.reference])).status_code, 404)
        self.assertEqual(self.client.post(reverse("bookings:cancel", args=[booking.reference])).status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_cancel_from_page(self):
        booking = self.reserve(1)
        self.client.post(reverse("bookings:cancel", args=[booking.reference]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(self.allocated(), 0)

    def test_sign_in_required(self):
        self.client.logout()
        response = self.client.get(reverse("bookings:details", args=[self.schedule.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
