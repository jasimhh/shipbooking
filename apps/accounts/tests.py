import re
from datetime import timedelta

from django.contrib.admin.sites import site
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import AuditLog
from apps.fleet.models import Port, Route, Vessel
from apps.operators.models import Operator, OperatorMembership
from apps.schedules.models import Schedule

from .admin import UserAdmin
from .models import User
from .permissions import can_edit_schedules, can_view_manifest, operators_for, role_required

PASSWORD = "harbour-lights-42"


def link_in(message):
    return re.search(r"https?://\S+", message.body).group(0)


class RegistrationAndVerificationTest(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, email="Asha@Example.com"):
        return self.client.post(reverse("accounts:register"), {
            "email": email, "first_name": "Asha", "last_name": "", "phone": "+91 98000 00000",
            "password1": PASSWORD, "password2": PASSWORD,
        })

    def test_register_sends_verification_and_link_confirms_once(self):
        self.assertRedirects(self.register(), reverse("accounts:verification_sent"))
        user = User.objects.get()
        self.assertEqual(user.email, "asha@example.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)

        link = link_in(mail.outbox[0])
        self.assertEqual(self.client.get(link).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(self.client.get(link).status_code, 400)  # single use

    def test_duplicate_email_rejected_case_insensitively(self):
        self.register()
        self.client.logout()
        response = self.register(email="ASHA@example.com")
        self.assertEqual(User.objects.count(), 1)
        self.assertIn("email", response.context["form"].errors)

    def test_resend_is_rate_limited(self):
        self.register()
        for _ in range(4):
            self.client.post(reverse("accounts:resend_verification"))
        self.assertEqual(len(mail.outbox), 1 + 3)


class LoginTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("pax@example.com", PASSWORD)

    def login(self, email="pax@example.com", password=PASSWORD):
        return self.client.post(reverse("accounts:login"), {"username": email, "password": password})

    def test_login_is_case_insensitive_and_logout_needs_post(self):
        self.assertRedirects(self.login(email="PAX@Example.com"), reverse("accounts:dashboard"))
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertRedirects(self.client.get(reverse("accounts:dashboard")),
                             f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}")

    def test_lockout_after_five_failures_even_with_right_password(self):
        for _ in range(5):
            self.assertEqual(self.login(password="wrong").status_code, 200)
        self.assertEqual(self.login().status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class PasswordAndProfileTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("pax@example.com", PASSWORD, first_name="Pax")

    def test_reset_flow_and_no_account_enumeration(self):
        url = reverse("accounts:password_reset")
        unknown = self.client.post(url, {"email": "nobody@example.com"})
        known = self.client.post(url, {"email": "PAX@example.com"})
        self.assertEqual(unknown.url, known.url)
        self.assertEqual(len(mail.outbox), 1)

        confirm = self.client.get(link_in(mail.outbox[0]), follow=True)
        new = "a-brand-new-passphrase-7"
        self.client.post(confirm.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))

    def test_profile_update_and_phone_validation(self):
        self.client.force_login(self.user)
        bad = self.client.post(reverse("accounts:profile"), {"first_name": "Pax", "phone": "call me"})
        self.assertIn("phone", bad.context["form"].errors)
        self.client.post(reverse("accounts:profile"), {"first_name": "Pax", "last_name": "Rao", "phone": "+91 98000 00000"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Rao")

    def test_account_pages_require_login(self):
        for name in ["dashboard", "profile", "password_change"]:
            self.assertEqual(self.client.get(reverse(f"accounts:{name}")).status_code, 302)


class PermissionsTest(TestCase):
    def setUp(self):
        self.op_a = Operator.objects.create(name="A")
        self.op_b = Operator.objects.create(name="B")
        self.staff = User.objects.create_user("staff@a.example", PASSWORD, role=User.Role.OPERATOR)
        OperatorMembership.objects.create(operator=self.op_a, user=self.staff, can_view_manifests=True)
        self.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)
        self.pax = User.objects.create_user("pax@example.com", PASSWORD)
        p1 = Port.objects.create(code="P1", name="P1", city="x", state="y")
        p2 = Port.objects.create(code="P2", name="P2", city="x", state="y")
        dep = timezone.now() + timedelta(days=1)

        def schedule(op):
            route = Route.objects.create(operator=op, origin=p1, destination=p2)
            vessel = Vessel.objects.create(operator=op, name=f"V{op.pk}")
            return Schedule.objects.create(route=route, vessel=vessel, departure_at=dep, arrival_at=dep + timedelta(hours=1))
        self.sailing_a, self.sailing_b = schedule(self.op_a), schedule(self.op_b)

    def test_operator_staff_see_only_their_operator(self):
        self.assertEqual(list(operators_for(self.staff)), [self.op_a])
        self.assertTrue(can_view_manifest(self.staff, self.sailing_a))
        self.assertFalse(can_view_manifest(self.staff, self.sailing_b))
        self.assertFalse(can_edit_schedules(self.staff, self.op_a))

    def test_inactive_membership_or_role_change_removes_access(self):
        self.staff.role = User.Role.PASSENGER
        self.staff.save()
        self.assertFalse(can_view_manifest(self.staff, self.sailing_a))
        self.assertEqual(list(operators_for(self.pax)), [])

    def test_admin_role_sees_everything_and_gets_staff(self):
        self.assertTrue(self.admin.is_staff)
        self.assertEqual(operators_for(self.admin).count(), 2)
        self.assertTrue(can_edit_schedules(self.admin, self.op_b))

    def test_role_required(self):
        view = role_required(User.Role.SUPPORT)(lambda request: HttpResponse("ok"))
        request = RequestFactory().get("/x")
        request.user = self.pax
        with self.assertRaises(PermissionDenied):
            view(request)
        request.user = self.admin
        self.assertEqual(view(request).status_code, 200)

    def test_role_changes_in_admin_are_audited(self):
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        self.pax.role = User.Role.SUPPORT
        UserAdmin(User, site).save_model(request, self.pax, form=None, change=True)
        entry = AuditLog.objects.get(action="user.access_changed")
        self.assertEqual(entry.changes["role"], ["passenger", "support"])
        self.assertEqual(entry.actor, self.admin)


class AbuseLimitTest(TestCase):
    def test_password_reset_capped_per_email(self):
        url = reverse("accounts:password_reset")
        codes = [self.client.post(url, {"email": "victim@example.com"}).status_code for _ in range(4)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(len(mail.outbox), 0)  # no such account, but the cap applies all the same

    def test_login_failures_capped_per_ip_across_accounts(self):
        url = reverse("accounts:login")
        for i in range(50):
            self.client.post(url, {"username": f"user{i}@example.com", "password": "Password123"})
        self.assertEqual(self.client.post(url, {"username": "new@example.com", "password": "x"}).status_code, 429)

    @override_settings(TRUSTED_PROXY_HEADER="HTTP_X_REAL_IP")
    def test_client_ip_from_trusted_proxy_header(self):
        from apps.common import client_ip

        request = RequestFactory().get("/", HTTP_X_REAL_IP="203.0.113.9", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(client_ip(request), "203.0.113.9")


class AdminShortcutTest(TestCase):
    def test_admin_button_only_for_admins(self):
        admin = User.objects.create_user("boss@example.com", "harbour-lights-42", role=User.Role.ADMIN)
        passenger = User.objects.create_user("pax2@example.com", "harbour-lights-42")
        self.client.force_login(passenger)
        self.assertNotContains(self.client.get("/"), "data-admin-url")
        self.client.force_login(admin)
        page = self.client.get("/")
        self.assertContains(page, 'data-admin-url="/admin/"')
        self.assertContains(page, '>Admin</a>')
