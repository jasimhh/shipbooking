"""E-tickets. The QR code holds only a verification URL with a random token: no names or other personal data."""

from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.bookings.models import Booking

from .models import Ticket, TicketVerificationEvent

NAVY = colors.HexColor("#07121F")
SEA = colors.HexColor("#5EEAD4")
MUTED = colors.HexColor("#4A5D6E")


@transaction.atomic
def issue(booking, by=None):
    """Void any valid ticket for the booking and issue a fresh one (first issue or reissue)."""
    Ticket.objects.filter(booking=booking, status=Ticket.Status.VALID).update(status=Ticket.Status.VOID, voided_at=timezone.now())
    return Ticket.objects.create(booking=booking, issued_by=by)


def void_all(booking):
    Ticket.objects.filter(booking=booking).exclude(status=Ticket.Status.VOID).update(status=Ticket.Status.VOID, voided_at=timezone.now())


def verify_url(ticket):
    return settings.SITE_URL + reverse("tickets:verify", args=[ticket.verification_token])


def check(token, user, ip=None):
    """Look up a scanned ticket for staff and log the scan. Returns (ticket or None, result)."""
    ticket = Ticket.objects.select_related("booking__schedule__route").filter(verification_token=token).first()
    if ticket is None:
        result = TicketVerificationEvent.Result.NOT_FOUND
    elif ticket.status == Ticket.Status.VOID or ticket.booking.status != Booking.Status.CONFIRMED:
        result = TicketVerificationEvent.Result.VOID
    elif ticket.status == Ticket.Status.BOARDED:
        result = TicketVerificationEvent.Result.ALREADY_BOARDED
    else:
        result = TicketVerificationEvent.Result.VALID
    TicketVerificationEvent.objects.create(ticket=ticket, result=result, verified_by=user, ip_address=ip or None)
    return ticket, result


def mark_boarded(ticket):
    return bool(Ticket.objects.filter(pk=ticket.pk, status=Ticket.Status.VALID).update(status=Ticket.Status.BOARDED))


def render_pdf(ticket):
    booking = ticket.booking
    schedule = booking.schedule
    route = schedule.route
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle(f"Ship Booking e-ticket {booking.reference}")
    width, height = A4
    left, top = 18 * mm, height - 18 * mm

    pdf.setFillColor(NAVY)
    pdf.roundRect(left, top - 40 * mm, width - 36 * mm, 40 * mm, 4 * mm, fill=1, stroke=0)
    pdf.setFillColor(SEA)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left + 8 * mm, top - 10 * mm, "SHIP BOOKING · E-TICKET")
    pdf.setFillColor(colors.white)
    title = f"{route.origin.name}  ->  {route.destination.name}"
    room = width - 2 * left - 16 * mm
    size = 20
    while size > 11 and pdf.stringWidth(title, "Helvetica-Bold", size) > room:
        size -= 1  # shrink long port names to fit the banner
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(left + 8 * mm, top - 21 * mm, title)
    pdf.setFont("Helvetica", 11)
    local_dep = timezone.localtime(schedule.departure_at)
    local_arr = timezone.localtime(schedule.arrival_at)
    pdf.drawString(left + 8 * mm, top - 30 * mm, f"Departs {local_dep:%a %d %b %Y, %H:%M}   ·   Arrives {local_arr:%H:%M}   ·   {schedule.vessel.name}")
    if route.operator.is_demo:
        pdf.setFillColor(colors.HexColor("#FCD34D"))
        pdf.drawString(left + 8 * mm, top - 36 * mm, "DEMO DATA: fictional sailing, not valid for travel")

    y = top - 54 * mm
    pdf.setFillColor(NAVY)
    rows = [
        ("Booking reference", booking.reference),
        ("Ticket number", ticket.number),
        ("Class", booking.fare_snapshot.get("cabin_class", "")),
        ("Operator", route.operator.name),
        ("Total paid", f"INR {booking.total_amount:,.2f}"),
    ]
    for label, value in rows:
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(MUTED)
        pdf.drawString(left, y, label.upper())
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColor(NAVY)
        pdf.drawString(left + 45 * mm, y, str(value))
        y -= 8 * mm

    y -= 4 * mm
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left, y, "Passengers")
    y -= 7 * mm
    pdf.setFont("Helvetica", 11)
    for p in booking.passengers.select_related("seat__seat"):
        seat = f"   Seat {p.seat.seat.number}" if hasattr(p, "seat") and p.seat.active_schedule_id else ""
        pdf.drawString(left, y, f"{p.full_name}   (age {p.age}){seat}")
        y -= 6 * mm

    qr = QrCodeWidget(verify_url(ticket))
    x0, y0, x1, y1 = qr.getBounds()
    size = 52 * mm
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(qr)
    renderPDF.draw(drawing, pdf, width - 18 * mm - size, top - 54 * mm - size + 8 * mm)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(width - 18 * mm, top - 54 * mm - size + 4 * mm, "Show this code at the port")

    pdf.setFont("Helvetica", 9)
    pdf.drawString(left, 30 * mm, "Arrive by the operator's reporting time and carry the ID your route requires.")
    pdf.drawString(left, 25 * mm, f"Boarding and travel guidance: {settings.SITE_URL}{reverse('pages:help')}")
    pdf.drawString(left, 20 * mm, f"Issued {timezone.localtime(ticket.issued_at):%d %b %Y %H:%M}. A reissued ticket replaces all earlier ones.")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()
