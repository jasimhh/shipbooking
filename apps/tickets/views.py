from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import can_view_manifest
from apps.bookings.models import Booking
from apps.common import client_ip
from apps.compliance.models import AuditLog

from . import services
from .models import Ticket


@login_required
def ticket_pdf(request, reference):
    booking = get_object_or_404(Booking, reference=reference, user=request.user, status=Booking.Status.CONFIRMED)
    ticket = booking.tickets.filter(status__in=[Ticket.Status.VALID, Ticket.Status.BOARDED]).order_by("-issued_at").first()
    if ticket is None:
        raise Http404
    response = HttpResponse(services.render_pdf(ticket), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="ship-booking-{booking.reference}.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response


def _can_check(user, ticket):
    if user.is_platform_admin or user.role == User.Role.SUPPORT:
        return True
    return ticket is not None and can_view_manifest(user, ticket.booking.schedule)


@login_required
def verify(request, token):
    """What port staff see when they scan a ticket's QR code."""
    ticket = Ticket.objects.select_related("booking__schedule__route__origin", "booking__schedule__route__destination").filter(verification_token=token).first()
    if not _can_check(request.user, ticket):
        raise PermissionDenied
    ticket, result = services.check(token, request.user, client_ip(request))
    return render(request, "tickets/verify.html", {
        "ticket": ticket, "result": result,
        "passengers": ticket.booking.passengers.select_related("seat__seat") if ticket else [],
    })


@login_required
@require_POST
def board(request, token):
    ticket = get_object_or_404(Ticket, verification_token=token)
    if not _can_check(request.user, ticket):
        raise PermissionDenied
    if ticket.booking.status == Booking.Status.CONFIRMED and services.mark_boarded(ticket):
        AuditLog.record(request.user, "ticket.boarded", ticket, {}, request)
        messages.success(request, "Marked as boarded.")
    else:
        messages.error(request, "This ticket can't be marked as boarded.")
    return redirect("tickets:verify", token=token)
