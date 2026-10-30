import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.bookings.models import Booking
from apps.bookings.services import expire_holds

from . import gateway, services
from .models import PaymentTransaction

log = logging.getLogger(__name__)


@login_required
def pay(request, reference):
    expire_holds()
    booking = get_object_or_404(Booking.objects.select_related("schedule__route__origin", "schedule__route__destination", "hold"),
                                reference=reference, user=request.user)
    try:
        txn = services.start_payment(booking)
    except services.PaymentError as e:
        if not gateway.is_configured() and booking.status == Booking.Status.PENDING:
            return render(request, "payments/pay.html", {"booking": booking, "not_configured": True})
        messages.error(request, str(e))
        return redirect("bookings:detail", reference=reference)
    route = booking.schedule.route
    return render(request, "payments/pay.html", {
        "booking": booking,
        "checkout": {
            "key": settings.RAZORPAY_KEY_ID,
            "order_id": txn.gateway_order_id,
            "amount": gateway.to_paise(txn.amount),
            "currency": "INR",
            "name": "Ship Booking",
            "description": f"{route.origin.name} to {route.destination.name} · {booking.reference}",
            "prefill": {"email": booking.contact_email, "contact": booking.contact_phone},
            "notes": {"booking": booking.reference},
        },
    })


@login_required
@require_POST
def checkout_return(request, reference):
    """Razorpay Checkout posts here after the passenger pays. The browser's word is never trusted on its own."""
    booking = get_object_or_404(Booking, reference=reference, user=request.user)
    order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    txn = get_object_or_404(PaymentTransaction, booking=booking, gateway_order_id=order_id)
    try:
        gateway.verify_checkout(order_id, payment_id, request.POST.get("razorpay_signature", ""))
    except gateway.SignatureError:
        log.warning("Bad checkout signature for %s", reference)
        messages.error(request, "We couldn't verify that payment. You haven't been charged twice; contact support if money left your account.")
        return redirect("bookings:detail", reference=reference)
    try:
        services.record_success(txn, payment_id, signature_verified=True)
    except services.PaymentError as e:
        messages.error(request, str(e))
        return redirect("bookings:detail", reference=reference)
    booking.refresh_from_db()
    if booking.status == Booking.Status.CONFIRMED:
        messages.success(request, f"Payment received. Booking {booking.reference} is confirmed.")
    else:
        messages.warning(request, "We received your payment, but the reservation had already been released. A full refund has been queued.")
    return redirect("bookings:detail", reference=reference)


@login_required
@require_POST
def checkout_failed(request, reference):
    booking = get_object_or_404(Booking, reference=reference, user=request.user)
    txn = PaymentTransaction.objects.filter(booking=booking, gateway_order_id=request.POST.get("razorpay_order_id", "")).first()
    if txn:
        services.record_failure(txn, request.POST.get("reason", "Payment failed at checkout"))
    messages.error(request, "The payment didn't go through. You can try again while your places are held.")
    return redirect("bookings:detail", reference=reference)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    try:
        outcome = services.handle_webhook(
            request.body.decode("utf-8"),
            request.headers.get("X-Razorpay-Signature", ""),
            request.headers.get("X-Razorpay-Event-Id", ""),
        )
    except gateway.SignatureError:
        log.warning("Rejected Razorpay webhook with an invalid signature")
        return HttpResponseBadRequest("invalid signature")
    except ValueError:
        return HttpResponseBadRequest("invalid body")
    return HttpResponse(outcome)
