from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.compliance.models import AuditLog
from apps.fleet.models import CabinClass, Port, Route, Vessel
from apps.schedules.models import Fare, Schedule

from .models import Operator, OperatorMembership

PASSWORD = "harbour-lights-42"


class Fleet:
    """Two verified operators, each with a route, vessel, cabin class and a draft sailing tomorrow."""

    def make(self):
        self.p1 = Port.objects.create(code="P1", name="Port One", city="x", state="y")
        self.p2 = Port.objects.create(code="P2", name="Port Two", city="x", state="y")
        self.dep = timezone.now() + timedelta(days=1)
        self.a, self.b = (self.operator(n) for n in ("Alpha", "Bravo"))

    def operator(self, name):
        op = Operator.objects.create(name=name, verification_status=Operator.Verification.VERIFIED)
        op.route = Route.objects.create(operator=op, origin=self.p1, destination=self.p2)
        op.vessel = Vessel.objects.create(operator=op, name=f"MV {name}")
        op.cabin = CabinClass.objects.create(vessel=op.vessel, code="DECK", name="Deck", capacity=50)
        op.sailing = Schedule.objects.create(route=op.route, vessel=op.vessel, departure_at=self.dep,
                                             arrival_at=self.dep + timedelta(hours=2))
        return op


class ValidationTest(Fleet, TestCase):
    def setUp(self):
        self.make()

    def test_vessel_cannot_sail_twice_at_once(self):
        clash = Schedule(route=self.a.route, vessel=self.a.vessel,
                         departure_at=self.dep + timedelta(hours=1), arrival_at=self.dep + timedelta(hours=3))
        with self.assertRaises(ValidationError) as e:
            clash.full_clean()
        self.assertIn("departure_at", e.exception.message_dict)
        self.a.sailing.status = Schedule.Status.CANCELLED
        self.a.sailing.save()
        clash.full_clean()  # a cancelled sailing frees the vessel

    def test_route_and_vessel_must_share_operator(self):
        with self.assertRaises(ValidationError):
            Schedule(route=self.a.route, vessel=self.b.vessel, departure_at=self.dep + timedelta(days=2),
                     arrival_at=self.dep + timedelta(days=2, hours=1)).full_clean()

    def test_fare_rules(self):
        fare = Fare(schedule=self.a.sailing, cabin_class=self.a.cabin, base_fare=Decimal("100"))
        fare.full_clean()
        self.assertEqual(fare.capacity, 50)  # blank capacity defaults to the cabin class
        for bad in [Fare(schedule=self.a.sailing, cabin_class=self.b.cabin, base_fare=1),
                    Fare(schedule=self.a.sailing, cabin_class=self.a.cabin, base_fare=1, capacity=51),
                    Fare(schedule=self.a.sailing, cabin_class=self.a.cabin, base_fare=1, capacity=5, units_allocated=6)]:
            with self.assertRaises(ValidationError):
                bad.clean()

    def test_membership_needs_operator_role(self):
        pax = User.objects.create_user("pax@example.com", PASSWORD)
        with self.assertRaises(ValidationError):
            OperatorMembership(operator=self.a, user=pax).full_clean()

    def test_publish_problems(self):
        self.assertEqual(self.a.sailing.publish_problems(), ["it has no fares"])
        Fare.objects.create(schedule=self.a.sailing, cabin_class=self.a.cabin, base_fare=10, capacity=50)
        self.assertEqual(self.a.sailing.publish_problems(), [])


class OperatorPortalTest(Fleet, TestCase):
    def setUp(self):
        self.make()
        self.staff = User.objects.create_user("staff@alpha.example", PASSWORD, role=User.Role.OPERATOR)
        self.member = OperatorMembership.objects.create(operator=self.a, user=self.staff, can_edit_schedules=True)
        self.client.force_login(self.staff)

    def url(self, name, *args):
        return reverse(f"operator:schedules_schedule_{name}", args=args)

    def form(self, sailing=None, **overrides):
        dep = self.dep + timedelta(days=3)
        data = {
            "route": self.a.route.pk, "vessel": self.a.vessel.pk,
            "departure_at_0": dep.date().isoformat(), "departure_at_1": "09:00",
            "arrival_at_0": dep.date().isoformat(), "arrival_at_1": "11:00",
            "status": "draft", "status_note": "",
            "fares-TOTAL_FORMS": "0", "fares-INITIAL_FORMS": "0",
        }
        if sailing:
            local = timezone.localtime(sailing.departure_at)
            data.update(departure_at_0=local.date().isoformat(), departure_at_1=local.strftime("%H:%M"),
                        arrival_at_0=local.date().isoformat(), arrival_at_1=(local + timedelta(hours=2)).strftime("%H:%M"))
        data.update(overrides)
        return data

    def test_sees_only_own_operator(self):
        listing = self.client.get(self.url("changelist"))
        self.assertEqual([s.pk for s in listing.context["cl"].result_list], [self.a.sailing.pk])
        self.assertNotEqual(self.client.get(self.url("change", self.b.sailing.pk)).status_code, 200)

    def test_cannot_pick_another_operators_route(self):
        response = self.client.post(self.url("add"), self.form(route=self.b.route.pk, vessel=self.b.vessel.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("route", response.context["adminform"].form.errors)

    def test_can_draft_and_submit_but_not_publish(self):
        response = self.client.post(self.url("add"), self.form(status="pending_approval"))
        self.assertEqual(response.status_code, 302)
        created = Schedule.objects.latest("pk")
        self.assertEqual(created.status, Schedule.Status.PENDING_APPROVAL)
        self.assertTrue(AuditLog.objects.filter(action="schedule.created", object_id=str(created.pk)).exists())

        response = self.client.post(self.url("change", created.pk), self.form(status="published"))
        self.assertIn("status", response.context["adminform"].form.errors)

    def test_live_sailing_only_status_can_change(self):
        Schedule.objects.filter(pk=self.a.sailing.pk).update(status=Schedule.Status.PUBLISHED)
        page = self.client.get(self.url("change", self.a.sailing.pk))
        self.assertIn("departure_at", page.context["adminform"].readonly_fields)
        self.client.post(self.url("change", self.a.sailing.pk),
                         self.form(self.a.sailing, status="delayed", status_note="Weather"))
        self.a.sailing.refresh_from_db()
        self.assertEqual((self.a.sailing.status, self.a.sailing.status_note), ("delayed", "Weather"))

    def test_view_only_member_cannot_add_or_change(self):
        self.member.can_edit_schedules = False
        self.member.save()
        self.assertEqual(self.client.get(self.url("add")).status_code, 403)
        before = self.a.sailing.status
        self.client.post(self.url("change", self.a.sailing.pk), self.form(self.a.sailing, status="pending_approval"))
        self.a.sailing.refresh_from_db()
        self.assertEqual(self.a.sailing.status, before)

    def test_passengers_refused_and_visitors_sent_to_sign_in(self):
        self.client.force_login(User.objects.create_user("pax@example.com", PASSWORD))
        self.assertEqual(self.client.get(reverse("operator:index")).status_code, 403)
        self.assertEqual(self.client.get(self.url("change", self.a.sailing.pk)).status_code, 403)
        self.client.logout()
        response = self.client.get(reverse("operator:index"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], f"{reverse('accounts:login')}?next={reverse('operator:index')}")


class AdminPublishTest(Fleet, TestCase):
    def setUp(self):
        self.make()
        self.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN, is_superuser=True)
        self.client.force_login(self.admin)

    def test_publish_action_needs_fares_and_is_audited(self):
        url = reverse("admin:schedules_schedule_changelist")
        sailings = [self.a.sailing.pk, self.b.sailing.pk]
        Fare.objects.create(schedule=self.a.sailing, cabin_class=self.a.cabin, base_fare=10, capacity=50)
        self.client.post(url, {"action": "publish", "_selected_action": sailings})
        self.a.sailing.refresh_from_db()
        self.b.sailing.refresh_from_db()
        self.assertEqual(self.a.sailing.status, Schedule.Status.PUBLISHED)
        self.assertEqual(self.b.sailing.status, Schedule.Status.DRAFT)  # no fares
        self.assertTrue(AuditLog.objects.filter(action="schedule.published", object_id=str(self.a.sailing.pk)).exists())

    def test_verify_action_audited(self):
        self.b.verification_status = Operator.Verification.PENDING
        self.b.save()
        self.client.post(reverse("admin:operators_operator_changelist"), {"action": "mark_verified", "_selected_action": [self.b.pk]})
        self.b.refresh_from_db()
        self.assertEqual(self.b.verification_status, Operator.Verification.VERIFIED)
        self.assertTrue(AuditLog.objects.filter(action="operator.verification_changed").exists())
