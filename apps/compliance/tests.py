import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, BookingPassenger, CancellationRule
from apps.bookings.tests import PASSWORD, BookingSetup
from apps.schedules.models import Schedule

from .models import AuditLog, ConsentRecord, CookiePreference, PolicyVersion, PrivacyRequest
from .privacy import StillTravelling, anonymise_user, apply_retention
from .views import read_consent


class FakeRequest:
    def __init__(self, value):
        self.COOKIES = {"cookie_consent": value}


class CookieConsentTest(TestCase):
    def test_banner_until_a_choice_is_made(self):
        self.assertContains(self.client.get("/"), 'class="cookie-banner"')
        response = self.client.post(reverse("compliance:save_cookies"), {"choice": "reject", "next": "/faq/"})
        self.assertRedirects(response, "/faq/")
        self.assertTrue(response.cookies["cookie_consent"].value.startswith("a0m0."))
        self.assertNotContains(self.client.get("/"), 'class="cookie-banner"')

    def test_each_choice_is_recorded_as_evidence(self):
        self.client.post(reverse("compliance:save_cookies"), {"choice": "accept"})
        pref = CookiePreference.objects.get()
        self.assertTrue(pref.analytics and pref.marketing and pref.anonymous_id)
        self.client.post(reverse("compliance:save_cookies"), {"choice": "custom", "analytics": "on"})
        pref.refresh_from_db()
        self.assertEqual((pref.analytics, pref.marketing), (True, False))  # same visitor, updated not duplicated
        self.assertEqual(CookiePreference.objects.count(), 1)
        self.assertEqual(ConsentRecord.objects.count(), 4)
        self.assertEqual(ConsentRecord.objects.filter(purpose="marketing").latest("pk").granted, False)

    def test_signed_in_choice_belongs_to_the_account(self):
        user = User.objects.create_user("a@example.com", PASSWORD)
        self.client.force_login(user)
        self.client.post(reverse("compliance:save_cookies"), {"choice": "reject"})
        self.assertEqual(CookiePreference.objects.get().user, user)

    def test_no_open_redirect_and_bad_cookie_means_undecided(self):
        response = self.client.post(reverse("compliance:save_cookies"), {"choice": "reject", "next": "https://evil.example/"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertFalse(read_consent(FakeRequest("a2m0.x"))["decided"])
        self.assertFalse(read_consent(FakeRequest("junk"))["decided"])
        self.assertEqual(read_consent(FakeRequest("a1m0.abc"))["analytics"], True)

    def test_fonts_are_self_hosted(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn("css/fonts.css", html)


class PrivacyCentreTest(BookingSetup, TestCase):
    def setUp(self):
        cache.clear()
        self.make()
        self.booking = self.reserve(2)

    def test_signed_out_visitors_are_asked_to_sign_in(self):
        self.assertContains(self.client.get(reverse("compliance:privacy")), "Sign in")
        self.assertEqual(self.client.get(reverse("compliance:my_data")).status_code, 302)

    def test_request_is_saved_audited_and_rate_limited(self):
        self.client.force_login(self.user)
        for _ in range(5):
            self.client.post(reverse("compliance:privacy"), {"request_type": "correction", "details": "Name spelt wrong"})
        self.assertContains(self.client.post(reverse("compliance:privacy"), {"request_type": "access"}), "several requests")
        self.assertEqual(PrivacyRequest.objects.filter(user=self.user, email="pax@example.com").count(), 5)
        self.assertTrue(AuditLog.objects.filter(action="privacy_request.created").exists())

    def test_download_contains_own_data_only(self):
        self.reserve(1, user=self.other)
        self.client.force_login(self.user)
        response = self.client.get(reverse("compliance:my_data"))
        data = json.loads(response.content)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(data["account"]["email"], "pax@example.com")
        self.assertEqual([b["reference"] for b in data["bookings"]], [self.booking.reference])
        self.assertEqual(len(data["bookings"][0]["passengers"]), 2)
        self.assertTrue(AuditLog.objects.filter(action="privacy.data_exported").exists())

    def test_anonymise_refuses_upcoming_trip_then_erases_identity(self):
        with self.assertRaises(StillTravelling):
            anonymise_user(self.user)
        Schedule.objects.filter(pk=self.schedule.pk).update(departure_at=timezone.now() - timedelta(days=1),
                                                            arrival_at=timezone.now() - timedelta(hours=20))
        anonymise_user(self.user)
        self.user.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.user.email, f"deleted-{self.user.pk}@deleted.invalid")
        self.assertFalse(self.user.is_active or self.user.has_usable_password())
        self.assertEqual((self.booking.contact_phone, self.booking.total_amount > 0), ("", True))
        self.assertEqual(set(self.booking.passengers.values_list("full_name", flat=True)), {"Removed"})
        self.assertFalse(self.client.login(email="pax@example.com", password=PASSWORD))

    def test_admin_action_completes_deletion_request(self):
        Schedule.objects.filter(pk=self.schedule.pk).update(departure_at=timezone.now() - timedelta(days=1),
                                                            arrival_at=timezone.now() - timedelta(hours=20))
        req = PrivacyRequest.objects.create(user=self.user, email=self.user.email, request_type="deletion")
        admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN, is_superuser=True)
        self.client.force_login(admin)
        self.client.post(reverse("admin:compliance_privacyrequest_changelist"),
                         {"action": "anonymise_accounts", "_selected_action": [req.pk]})
        req.refresh_from_db()
        self.assertEqual(req.status, PrivacyRequest.Status.COMPLETED)
        self.assertTrue(AuditLog.objects.filter(action="user.anonymised").exists())


@override_settings(RETENTION={"abandoned_booking_days": 30, "notification_days": 180, "anonymous_cookie_days": 365})
class RetentionTest(BookingSetup, TestCase):
    def test_old_abandoned_bookings_are_scrubbed_recent_ones_kept(self):
        self.make()
        old, recent = self.reserve(1), self.reserve(1)
        Booking.objects.filter(pk__in=[old.pk, recent.pk]).update(status=Booking.Status.EXPIRED)
        Booking.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=31))
        CookiePreference.objects.create(anonymous_id="x")
        CookiePreference.objects.filter(anonymous_id="x").update(updated_at=timezone.now() - timedelta(days=400))
        counts = apply_retention()
        self.assertEqual(counts["abandoned_bookings_scrubbed"], 1)
        self.assertEqual(counts["anonymous_cookie_choices_deleted"], 1)
        self.assertEqual(BookingPassenger.objects.get(booking=old).full_name, "Removed")
        self.assertEqual(BookingPassenger.objects.get(booking=recent).full_name, "Passenger 0")
        self.assertEqual(apply_retention()["abandoned_bookings_scrubbed"], 0)  # idempotent


class PolicyAndSeoTest(TestCase):
    def test_draft_shows_unconfigured_facts_instead_of_inventing_them(self):
        response = self.client.get(reverse("pages:policy", args=["grievance"]))
        self.assertContains(response, "Draft")
        self.assertContains(response, "Grievance officer: not yet configured")

    @override_settings(BUSINESS={"legal_entity_name": "Example Ferries Pvt Ltd", "registered_address": "", "support_email": "",
                                 "support_phone": "", "grievance_officer_name": "", "grievance_officer_email": "",
                                 "platform_role": "intermediary"})
    def test_draft_uses_configured_facts(self):
        response = self.client.get(reverse("pages:policy", args=["privacy"]))
        self.assertContains(response, "Example Ferries Pvt Ltd")
        self.assertContains(response, "a booking intermediary")

    def test_cancellation_bands_come_only_from_the_approved_policy(self):
        self.assertContains(self.client.get(reverse("pages:policy", args=["cancellation"])), "have not been approved")
        policy = PolicyVersion.objects.create(policy_type="cancellation", version="1", body="Approved text",
                                              effective_from=timezone.now() - timedelta(days=1), is_published=True)
        CancellationRule.objects.create(policy=policy, min_hours_before_departure=48, refund_percent=75)
        self.assertContains(self.client.get(reverse("pages:policy", args=["cancellation"])), "Approved text")
        self.assertContains(self.client.get(reverse("pages:policy", args=["refund"])), "Draft")

    def test_every_policy_draft_renders(self):
        for value in PolicyVersion.PolicyType.values:
            self.assertEqual(self.client.get(reverse("pages:policy", args=[value])).status_code, 200, value)

    @override_settings(SITE_URL="https://shipbooking.example")
    def test_robots_sitemap_canonical_and_private_noindex(self):
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /account/", robots)
        self.assertIn("Sitemap: https://shipbooking.example/sitemap.xml", robots)
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>https://shipbooking.example/policies/privacy/</loc>", sitemap)
        self.assertNotIn("/account/", sitemap)
        self.assertContains(self.client.get("/faq/?utm=x"), '<link rel="canonical" href="https://shipbooking.example/faq/">')
        self.assertEqual(self.client.get("/account/sign-in/")["X-Robots-Tag"], "noindex, nofollow")
        self.assertNotIn("X-Robots-Tag", self.client.get("/faq/"))
