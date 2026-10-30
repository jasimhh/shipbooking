"""Personal-data export, account anonymisation and retention clean-up."""
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PassengerProfile
from apps.bookings.models import Booking, BookingPassenger
from apps.support.models import Notification, SupportMessage, SupportTicket

from .models import AuditLog, ConsentRecord, CookiePreference, PrivacyRequest

REMOVED = "Removed"
ACTIVE = [Booking.Status.PENDING, Booking.Status.CONFIRMED]


def _when(value):
    return value.isoformat() if value else None


def export_user_data(user):
    """Everything we hold about a person, in plain JSON-ready structures."""
    profile = PassengerProfile.objects.filter(user=user).first()
    bookings = (Booking.objects.filter(user=user)
                .select_related("schedule__route__origin", "schedule__route__destination", "schedule__vessel", "fare__cabin_class")
                .prefetch_related("passengers", "tickets", "payments__refunds", "cancellation_requests"))
    tickets = SupportTicket.objects.filter(user=user).prefetch_related("messages")
    return {
        "exported_at": _when(timezone.now()),
        "account": {"email": user.email, "first_name": user.first_name, "last_name": user.last_name, "phone": user.phone,
                    "role": user.role, "email_verified": user.email_verified, "joined": _when(user.date_joined),
                    "last_login": _when(user.last_login)},
        "profile": {"full_name": profile.full_name, "date_of_birth": _when(profile.date_of_birth)} if profile else None,
        "bookings": [{
            "reference": b.reference, "status": b.status, "created": _when(b.created_at),
            "sailing": {"from": b.schedule.route.origin.name, "to": b.schedule.route.destination.name,
                        "departure": _when(b.schedule.departure_at), "vessel": b.schedule.vessel.name,
                        "class": b.fare.cabin_class.name},
            "contact_email": b.contact_email, "contact_phone": b.contact_phone,
            "total": str(b.total_amount), "currency": b.currency,
            "passengers": [{"name": p.full_name, "age": p.age, "gender": p.gender} for p in b.passengers.all()],
            "tickets": [{"number": t.number, "status": t.status} for t in b.tickets.all()],
            "payments": [{"amount": str(p.amount), "status": p.status, "gateway_payment_id": p.gateway_payment_id,
                          "refunds": [{"amount": str(r.amount), "status": r.status} for r in p.refunds.all()]}
                         for p in b.payments.all()],
            "cancellation_requests": [{"status": c.status, "reason": c.reason, "created": _when(c.created_at)}
                                      for c in b.cancellation_requests.all()],
        } for b in bookings],
        "support_requests": [{
            "reference": t.reference, "subject": t.subject, "status": t.status, "created": _when(t.created_at),
            "messages": [{"from_staff": m.is_staff_reply, "body": m.body, "sent": _when(m.created_at)} for m in t.messages.all()],
        } for t in tickets],
        "notifications": list(Notification.objects.filter(user=user).values("channel", "subject", "status", "created_at")),
        "cookie_preferences": list(CookiePreference.objects.filter(user=user).values("analytics", "marketing", "updated_at")),
        "consent_records": list(ConsentRecord.objects.filter(user=user).values("purpose", "granted", "created_at")),
        "privacy_requests": list(PrivacyRequest.objects.filter(user=user).values("request_type", "status", "created_at", "resolution_note")),
    }


def scrub_bookings(bookings, placeholder_email):
    """Remove names and contact details but keep the financial record (amounts, references, statuses)."""
    BookingPassenger.objects.filter(booking__in=bookings).update(full_name=REMOVED, gender=BookingPassenger.Gender.UNDISCLOSED)
    return bookings.update(contact_email=placeholder_email, contact_phone="")


def upcoming_bookings(user):
    return Booking.objects.filter(user=user, status__in=ACTIVE, schedule__departure_at__gt=timezone.now())


class StillTravelling(Exception):
    pass


@transaction.atomic
def anonymise_user(user, actor=None, request=None):
    """Erase a person's identity on request. Refuses while they have upcoming trips that need their details."""
    if upcoming_bookings(user).exists():
        raise StillTravelling("This person has upcoming bookings. Cancel them or wait until after travel.")
    placeholder = f"deleted-{user.pk}@deleted.invalid"
    scrub_bookings(Booking.objects.filter(user=user), placeholder)
    SupportTicket.objects.filter(user=user).update(contact_email=placeholder)
    SupportMessage.objects.filter(author=user, is_staff_reply=False).update(body="[Removed at the customer's request]")
    Notification.objects.filter(user=user).update(recipient=placeholder, body="", subject="")
    PassengerProfile.objects.filter(user=user).delete()
    CookiePreference.objects.filter(user=user).delete()
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
    user.email = placeholder
    user.first_name = user.last_name = user.phone = ""
    user.is_active = user.email_verified = False
    user.set_unusable_password()
    user.save()
    AuditLog.record(actor, "user.anonymised", user, {}, request)


def apply_retention(now=None):
    """Clean up data past the retention periods in settings.RETENTION. Returns counts for the log."""
    now = now or timezone.now()
    days = settings.RETENTION
    abandoned = Booking.objects.filter(
        status__in=[Booking.Status.EXPIRED, Booking.Status.PAYMENT_FAILED],
        updated_at__lt=now - timedelta(days=days["abandoned_booking_days"]),
    ).exclude(contact_email="removed@deleted.invalid")
    counts = {
        "abandoned_bookings_scrubbed": scrub_bookings(abandoned, "removed@deleted.invalid"),
        "notifications_cleared": Notification.objects.filter(
            created_at__lt=now - timedelta(days=days["notification_days"])).exclude(body="").update(body=""),
        "anonymous_cookie_choices_deleted": CookiePreference.objects.filter(
            user__isnull=True, updated_at__lt=now - timedelta(days=days["anonymous_cookie_days"])).delete()[0],
    }
    return counts
