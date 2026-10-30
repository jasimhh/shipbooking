"""Passenger notifications. Each one is stored as a Notification row and emailed after the
surrounding transaction commits, so nobody is told about a change that was rolled back.
Admins can override any message with an active NotificationTemplate of the same key."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Channel, Notification, NotificationTemplate

log = logging.getLogger(__name__)

# key: (subject, message). Both are Django templates rendered with {booking, site_url, ...extra}.
MESSAGES = {
    "booking_reserved": ("Reservation {{ booking.reference }}: please complete payment",
                         "We're holding {{ booking.passenger_count }} place(s) for you until {{ booking.hold.expires_at|time:'H:i' }}. Pay before then to confirm your booking."),
    "booking_confirmed": ("Booking {{ booking.reference }} confirmed",
                          "Your payment was received and your booking is confirmed. Download your e-ticket: {{ site_url }}{% url 'tickets:pdf' booking.reference %}"),
    "payment_failed": ("Payment for {{ booking.reference }} didn't go through",
                       "Your payment failed. You can try again while your places are held: {{ site_url }}{% url 'bookings:detail' booking.reference %}"),
    "sailing_delayed": ("Delay to your sailing {{ booking.reference }}",
                        "Your sailing has been delayed.{% if booking.schedule.status_note %} Operator note: {{ booking.schedule.status_note }}{% endif %} Check the latest times: {{ site_url }}{% url 'pages:service_updates' %}"),
    "sailing_cancelled": ("Your sailing {{ booking.reference }} has been cancelled",
                          "The operator has cancelled this sailing.{% if booking.schedule.status_note %} Note: {{ booking.schedule.status_note }}{% endif %} Your booking is cancelled and a full refund has been queued."),
    "cancellation_requested": ("Cancellation request for {{ booking.reference }} received",
                               "We've received your cancellation request. We'll let you know the outcome."),
    "cancellation_approved": ("Booking {{ booking.reference }} cancelled",
                              "Your cancellation was approved.{% if refund %} A refund of ₹{{ refund.amount }} is being processed.{% else %} No refund is due under the cancellation policy.{% endif %}"),
    "cancellation_rejected": ("Cancellation request for {{ booking.reference }} declined",
                              "Your cancellation request was declined.{% if note %} Reason: {{ note }}{% endif %} Your booking remains valid."),
    "refund_processed": ("Refund for {{ booking.reference }} sent",
                         "We've sent a refund of ₹{{ refund.amount }}. Banks usually show it within 5 to 7 working days."),
    "refund_failed": ("Problem with your refund for {{ booking.reference }}",
                      "We couldn't complete your refund of ₹{{ refund.amount }}. Our team will contact you."),
}


def _render(source, ctx):
    return Template(source).render(Context(ctx)).strip()


def notify(key, booking, **extra):
    ctx = {"booking": booking, "site_url": settings.SITE_URL, **extra}
    override = NotificationTemplate.objects.filter(key=key, channel=Channel.EMAIL, is_active=True).first()
    subject_src, message_src = (override.subject, override.body) if override else MESSAGES[key]
    message = _render(message_src, ctx)
    body = render_to_string("emails/booking_update.txt", {**ctx, "message": message})
    notification = Notification.objects.create(
        user=booking.user, booking=booking, channel=Channel.EMAIL, recipient=booking.contact_email,
        template_key=key, subject=_render(subject_src, ctx)[:200], body=body,
    )
    transaction.on_commit(lambda: _send(notification.pk))
    return notification


def _send(pk):
    n = Notification.objects.get(pk=pk)
    try:
        send_mail(n.subject, n.body, None, [n.recipient])
    except Exception as e:  # keep the record; an admin can see and retry failures
        log.exception("Notification %s failed", pk)
        Notification.objects.filter(pk=pk).update(status=Notification.Status.FAILED, error=str(e)[:1000])
        return
    Notification.objects.filter(pk=pk).update(status=Notification.Status.SENT, sent_at=timezone.now())
