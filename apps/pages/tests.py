from datetime import timedelta
from io import StringIO
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import PolicyVersion
from apps.fleet.models import Port
from apps.schedules.models import Fare, Schedule
from apps.support.models import SupportTicket

from .templatetags.site import duration, inr


class FiltersTest(TestCase):
    def test_inr_uses_indian_grouping(self):
        self.assertEqual(inr(Decimal("125000")), "₹1,25,000")
        self.assertEqual(inr(Decimal("12345678.5")), "₹1,23,45,678.50")
        self.assertEqual(inr(Decimal("999")), "₹999")
        self.assertEqual(inr(Decimal("0")), "₹0")

    def test_duration(self):
        self.assertEqual(duration(timedelta(minutes=150)), "2 h 30 min")
        self.assertEqual(duration(timedelta(minutes=45)), "45 min")
        self.assertEqual(duration(timedelta(hours=3)), "3 h")


class PublicPagesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.tomorrow = timezone.localdate() + timedelta(days=1)

    def setUp(self):
        cache.clear()

    def search(self, **params):
        base = {"origin": "MUMFW", "destination": "MDWJ", "date": self.tomorrow.isoformat(), "passengers": 1}
        return self.client.get(reverse("pages:search"), base | params)

    def test_every_public_page_renders(self):
        schedule = Schedule.objects.first()
        urls = [
            reverse("pages:home"), reverse("pages:help"), reverse("pages:faq"), reverse("pages:contact"),
            reverse("pages:about"), reverse("pages:service_updates"), reverse("pages:sailing", args=[schedule.pk]),
        ]
        urls += [reverse("pages:guide", args=[s]) for s in
                 ["booking-guide", "boarding", "passenger-guidelines", "luggage", "travel-requirements", "safety"]]
        urls += [reverse("pages:policy", args=[p]) for p in PolicyVersion.PolicyType.values]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_home_route_cards_use_live_sailings(self):
        routes = self.client.get(reverse("pages:home")).context["routes"]
        self.assertEqual(len(routes), 4)
        card = next(r for r in routes if r["route"].origin.code == "MUMFW")
        self.assertEqual(card["from_price"], Decimal("487.50"))
        Schedule.objects.filter(route=card["route"]).update(status=Schedule.Status.CANCELLED)
        self.assertEqual(len(self.client.get(reverse("pages:home")).context["routes"]), 3)

    def test_unknown_pages_404(self):
        self.assertEqual(self.client.get(reverse("pages:guide", args=["nope"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("pages:policy", args=["nope"])).status_code, 404)

    def test_search_lists_tomorrows_sailings(self):
        response = self.search()
        self.assertEqual(len(response.context["results"]), 3)
        self.assertContains(response, "Demo")

    def test_search_rejects_identical_ports_and_past_dates(self):
        response = self.search(destination="MUMFW", date=(timezone.localdate() - timedelta(days=1)).isoformat())
        form = response.context["form"]
        self.assertIn("destination", form.errors)
        self.assertIn("date", form.errors)

    def test_draft_and_cancelled_sailings_not_bookable(self):
        sailings = Schedule.objects.filter(route__origin__code="MUMFW", route__destination__code="MDWJ",
                                           departure_at__date=self.tomorrow)
        draft, cancelled = sailings[0], sailings[1]
        Schedule.objects.filter(pk=draft.pk).update(status=Schedule.Status.DRAFT)
        Schedule.objects.filter(pk=cancelled.pk).update(status=Schedule.Status.CANCELLED)
        self.assertEqual(len(self.search().context["results"]), 1)
        self.assertEqual(self.client.get(reverse("pages:sailing", args=[draft.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("pages:service_updates")), "Cancelled")

    def test_sold_out_sailing_shown_as_not_enough_places(self):
        Fare.objects.filter(schedule__departure_at__date=self.tomorrow).update(units_allocated=0)
        for fare in Fare.objects.filter(schedule__departure_at__date=self.tomorrow):
            Fare.objects.filter(pk=fare.pk).update(units_allocated=fare.capacity)
        results = self.search().context["results"]
        self.assertTrue(results and not any(r["bookable"] for r in results))

    def test_sort_by_price(self):
        prices = [r["from_price"] for r in self.search(sort="price").context["results"]]
        self.assertEqual(prices, sorted(prices))

    def test_empty_day_suggests_other_dates(self):
        Schedule.objects.filter(departure_at__date=self.tomorrow).update(status=Schedule.Status.DRAFT)
        response = self.search()
        self.assertEqual(response.context["results"], [])
        self.assertTrue(response.context["other_dates"])

    def test_contact_creates_ticket_and_rate_limits(self):
        data = {"email": "p@example.com", "category": "booking", "subject": "Help", "message": "Hello"}
        for _ in range(5):
            self.assertEqual(self.client.post(reverse("pages:contact"), data).status_code, 302)
        self.assertEqual(SupportTicket.objects.count(), 5)
        self.assertEqual(SupportTicket.objects.first().messages.count(), 1)
        self.assertEqual(self.client.post(reverse("pages:contact"), data).status_code, 429)
        self.assertEqual(SupportTicket.objects.count(), 5)

    def test_contact_honeypot_stores_nothing(self):
        data = {"email": "b@example.com", "category": "other", "subject": "x", "message": "x", "website": "spam"}
        self.client.post(reverse("pages:contact"), data)
        self.assertFalse(SupportTicket.objects.exists())

    def test_published_policy_is_shown(self):
        PolicyVersion.objects.create(policy_type="privacy", version="1.0", body="Policy text here.",
                                     effective_from=timezone.now(), is_published=True)
        self.assertContains(self.client.get(reverse("pages:policy", args=["privacy"])), "Policy text here.")
