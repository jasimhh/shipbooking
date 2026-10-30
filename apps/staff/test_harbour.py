import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.serializers.json import DjangoJSONEncoder
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

from . import charts

PASSWORD = "harbour-lights-42"


class ChartsTest(TestCase):
    def sailing(self, dep_offset, minutes=60, status=Schedule.Status.PUBLISHED):
        now = timezone.now()
        return Schedule(departure_at=now + dep_offset, arrival_at=now + dep_offset + timedelta(minutes=minutes), status=status)

    def test_states_from_timetable(self):
        self.assertEqual(charts.sailing_state(self.sailing(timedelta(hours=3)))[0], "scheduled")
        self.assertEqual(charts.sailing_state(self.sailing(timedelta(minutes=20)))[0], "boarding")
        state, progress = charts.sailing_state(self.sailing(timedelta(minutes=-30)))
        self.assertEqual(state, "at_sea")
        self.assertAlmostEqual(progress, 0.5, places=2)
        self.assertEqual(charts.sailing_state(self.sailing(timedelta(hours=-3)))[0], "arrived")
        self.assertEqual(charts.sailing_state(self.sailing(timedelta(minutes=-30), status=Schedule.Status.CANCELLED))[0], "cancelled")

    def test_known_region_anchors_land_on_drawn_jetties(self):
        a = Port(pk=1, code="A", latitude=Decimal("18.958"), longitude=Decimal("72.846"), state="Maharashtra")
        b = Port(pk=2, code="B", latitude=Decimal("18.806"), longitude=Decimal("72.882"), state="Maharashtra")
        pos = charts.place_ports("maharashtra", [a, b])
        self.assertEqual(pos[1], (300, 362))
        self.assertEqual(pos[2], (690, 452))

    def test_unknown_region_fits_and_handles_missing_coordinates(self):
        a = Port(pk=1, latitude=Decimal("10"), longitude=Decimal("76"))
        b = Port(pk=2, latitude=Decimal("11"), longitude=Decimal("77"))
        c = Port(pk=3)
        pos = charts.place_ports("kerala", [a, b, c])
        self.assertTrue(all(0 <= x <= 1000 and 0 <= y <= 600 for x, y in pos.values()))
        self.assertLess(pos[2][1], pos[1][1])  # further north is higher up

    def test_dms(self):
        self.assertEqual(charts.dms(Decimal("18.958"), "N", "S"), "18°57′N")
        self.assertEqual(charts.dms(Decimal("-0.5"), "N", "S"), "0°30′S")


@override_settings(**KEYS)
class HarbourViewTest(BookingSetup, TestCase):
    def setUp(self):
        self.make()
        Port.objects.filter(code="P1").update(state="Maharashtra", latitude=Decimal("18.958"), longitude=Decimal("72.846"))
        Port.objects.filter(code="P2").update(state="Maharashtra", latitude=Decimal("18.806"), longitude=Decimal("72.882"))
        rzp = FakeRazorpay()
        for name in ["create_order", "fetch_payment", "capture"]:
            patcher = mock.patch(f"apps.payments.gateway.{name}", getattr(rzp, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        # move the sailing to depart in 20 minutes so it shows today as boarding
        dep = timezone.now() + timedelta(minutes=20)
        Schedule.objects.filter(pk=self.schedule.pk).update(departure_at=dep, arrival_at=dep + timedelta(hours=1))
        self.booking = self.reserve(2)
        txn = payments.start_payment(self.booking)
        payments.record_success(txn, rzp.pay(txn.gateway_order_id))

        other = Operator.objects.create(name="Other", verification_status=Operator.Verification.VERIFIED)
        ov = Vessel.objects.create(operator=other, name="MV Other")
        oc = CabinClass.objects.create(vessel=ov, code="D", name="Deck", capacity=10)
        p3 = Port.objects.create(code="P3", name="Port Three", city="x", state="Kerala")
        oroute = Route.objects.create(operator=other, origin=p3, destination=Port.objects.get(code="P2"))
        self.other_sailing = Schedule.objects.create(route=oroute, vessel=ov, departure_at=dep, arrival_at=dep + timedelta(hours=1),
                                                     status=Schedule.Status.PUBLISHED)
        Fare.objects.create(schedule=self.other_sailing, cabin_class=oc, base_fare=1, capacity=10)

        self.crew = User.objects.create_user("crew@op.example", PASSWORD, role=User.Role.OPERATOR)
        self.membership = OperatorMembership.objects.create(operator=self.schedule.route.operator, user=self.crew, can_view_manifests=True)
        self.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)

    def page(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("staff:harbour"))
        self.assertEqual(response.status_code, 200)
        return json.loads(json.dumps(response.context["data"], cls=DjangoJSONEncoder))

    def test_passengers_cannot_open(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("staff:harbour")).status_code, 403)

    def test_operator_sees_only_own_routes_and_live_state(self):
        data = self.page(self.crew)
        self.assertEqual([r["key"] for r in data["regions"]], ["maharashtra"])
        sailing = data["regions"][0]["sailings"][0]
        self.assertEqual((sailing["id"], sailing["state"], sailing["sold"]), (self.schedule.pk, "boarding", 2))
        self.assertEqual(data["regions"][0]["ports"][0]["x"] in (300, 690), True)
        self.assertEqual(data["stats"]["passengers"], 2)
        self.assertFalse(self.client.get(reverse("staff:harbour")).context["can_add_ferry"])

    def test_admin_sees_all_regions_and_unknown_region_on_grid(self):
        data = self.page(self.admin)
        keys = {r["key"]: r for r in data["regions"]}
        self.assertEqual(set(keys), {"maharashtra", "kerala"})
        self.assertIsNone(keys["kerala"]["art"])
        self.assertEqual(Decimal(data["stats"]["received"]), self.booking.total_amount)

    def test_passenger_list_permission_and_audit(self):
        self.client.force_login(self.crew)
        url = reverse("staff:harbour_passengers", args=[self.schedule.pk])
        rows = self.client.get(url).json()["passengers"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ticket"], "Valid")
        self.assertTrue(AuditLog.objects.filter(action="harbour.passengers_viewed").exists())
        self.assertEqual(self.client.get(reverse("staff:harbour_passengers", args=[self.other_sailing.pk])).status_code, 403)
        self.membership.can_view_manifests = False
        self.membership.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertIsNone(self.page(self.crew)["regions"][0]["sailings"][0]["passengers"])

    def test_delays_show_as_alerts(self):
        Schedule.objects.filter(pk=self.schedule.pk).update(status=Schedule.Status.DELAYED, status_note="Fog")
        alerts = self.page(self.crew)["alerts"]
        self.assertTrue(any("delayed" in a["title"] and a["detail"] == "Fog" for a in alerts))

    def test_add_ferry_admin_only_with_classes(self):
        data = {"name": "MV New", "operator": self.schedule.route.operator_id, "imo_number": "", "vessel_type": "Catamaran",
                "seating_mode": "capacity", "classes": "Deck · 120\nSeater: 60"}
        self.client.force_login(self.crew)
        self.assertEqual(self.client.post(reverse("staff:harbour_add_ferry"), data).status_code, 403)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse("staff:harbour_add_ferry"), data), reverse("staff:harbour"))
        vessel = Vessel.objects.get(name="MV New")
        self.assertEqual(sorted(vessel.cabin_classes.values_list("name", "capacity")), [("Deck", 120), ("Seater", 60)])
        self.assertTrue(AuditLog.objects.filter(action="vessel.created", object_id=str(vessel.pk)).exists())

    def test_add_ferry_rejects_unreadable_classes(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("staff:harbour_add_ferry"), {
            "name": "MV Bad", "operator": self.schedule.route.operator_id, "seating_mode": "capacity", "classes": "lots of seats"})
        self.assertFalse(Vessel.objects.filter(name="MV Bad").exists())

    def test_names_are_escaped_server_side_data(self):
        Port.objects.filter(code="P1").update(name='<img src=x onerror=alert(1)>')
        self.client.force_login(self.admin)
        html = self.client.get(reverse("staff:harbour")).content.decode()
        self.assertNotIn("<img src=x", html)  # json_script escapes < so it can't break out of the data tag
