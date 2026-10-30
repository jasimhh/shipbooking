"""Staff area at /staff/: dashboard, passenger manifests, reports and the support desk.

Access is checked on the server for every view. Operator staff only ever see their own
operators' sailings and figures; support staff see bookings but not money; admins see everything.
"""

import csv
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import can_view_manifest, operators_for, role_required
from apps.bookings.models import Booking, BookingPassenger, CancellationRequest
from apps.compliance.models import AuditLog
from apps.operators.models import Operator
from apps.payments.models import PaymentTransaction, Refund
from apps.schedules.models import Schedule
from apps.support.models import SupportMessage, SupportTicket
from apps.support.notifications import notify_support

staff_only = role_required(User.Role.SUPPORT, User.Role.OPERATOR)
support_only = role_required(User.Role.SUPPORT)

ZERO_MONEY = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
ZERO = Value(0, output_field=IntegerField())


def scope(user):
    """Operators whose sailings this user may report on."""
    if user.is_platform_admin or user.role == User.Role.SUPPORT:
        return Operator.objects.all()
    return operators_for(user)


def sees_money(user):
    return user.is_platform_admin or user.role == User.Role.OPERATOR


def with_occupancy(schedules):
    return schedules.annotate(
        capacity=Coalesce(Sum("fares__capacity"), ZERO),
        sold=Coalesce(Sum("fares__units_allocated"), ZERO),
    ).select_related("route__origin", "route__destination", "vessel")


@staff_only
def dashboard(request):
    user, now = request.user, timezone.now()
    ops = scope(user)
    bookings = Booking.objects.filter(schedule__route__operator__in=ops)
    week_ago = now - timedelta(days=7)
    context = {
        "upcoming": with_occupancy(Schedule.objects.filter(
            route__operator__in=ops, departure_at__gte=now, departure_at__lte=now + timedelta(days=7),
            status__in=Schedule.LIVE,
        )).order_by("departure_at")[:30],
        "confirmed_7d": bookings.filter(status=Booking.Status.CONFIRMED, confirmed_at__gte=week_ago).count(),
        "pending_now": bookings.filter(status=Booking.Status.PENDING).count(),
        "sees_money": sees_money(user),
        "is_support": user.is_platform_admin or user.role == User.Role.SUPPORT,
    }
    if context["sees_money"]:
        context["revenue_7d"] = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.CAPTURED, captured_at__gte=week_ago, booking__schedule__route__operator__in=ops,
        ).aggregate(t=Coalesce(Sum("amount"), ZERO_MONEY))["t"]
    if context["is_support"]:
        context["open_tickets"] = SupportTicket.objects.exclude(status__in=[SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED]).count()
        context["pending_cancellations"] = CancellationRequest.objects.filter(status=CancellationRequest.Status.REQUESTED).count()
    if user.is_platform_admin:
        context["pending_refunds"] = Refund.objects.filter(status__in=[Refund.Status.PENDING, Refund.Status.FAILED]).count()
        context["awaiting_approval"] = Schedule.objects.filter(status=Schedule.Status.PENDING_APPROVAL).count()
    return render(request, "staff/dashboard.html", context)


MANIFEST_COLUMNS = ["Booking", "Passenger", "Age", "Gender", "Seat", "Class", "Contact phone", "Ticket"]


@staff_only
def manifest(request, pk):
    schedule = get_object_or_404(Schedule.objects.select_related("route__origin", "route__destination", "route__operator", "vessel"), pk=pk)
    user = request.user
    if not (user.is_platform_admin or user.role == User.Role.SUPPORT or can_view_manifest(user, schedule)):
        raise PermissionDenied
    passengers = (
        BookingPassenger.objects.filter(booking__schedule=schedule, booking__status=Booking.Status.CONFIRMED)
        .select_related("booking", "seat__seat").prefetch_related("booking__tickets").order_by("booking__reference", "id")
    )
    rows = []
    for p in passengers:
        ticket = next((t for t in p.booking.tickets.all() if t.status != "void"), None)
        seat = p.seat.seat.number if hasattr(p, "seat") and p.seat.active_schedule_id else ""
        rows.append([p.booking.reference, p.full_name, p.age, p.get_gender_display(), seat,
                     p.booking.fare_snapshot.get("cabin_class", ""), p.booking.contact_phone,
                     ticket.get_status_display() if ticket else "No ticket"])

    export = request.GET.get("format") == "csv"
    AuditLog.record(user, "manifest.exported" if export else "manifest.viewed", schedule, {"passengers": len(rows)}, request)
    if export:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="manifest-{schedule.pk}-{schedule.departure_at:%Y%m%d-%H%M}.csv"'
        response["Cache-Control"] = "private, no-store"
        writer = csv.writer(response)
        writer.writerow(MANIFEST_COLUMNS)
        writer.writerows(rows)
        return response
    return render(request, "staff/manifest.html", {"schedule": schedule, "rows": rows, "columns": MANIFEST_COLUMNS})


class ReportForm(forms.Form):
    start = forms.DateField(label="From", widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="To", widget=forms.DateInput(attrs={"type": "date"}))
    operator = forms.ModelChoiceField(queryset=Operator.objects.none(), required=False, empty_label="All operators")

    def __init__(self, *args, operators, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields["operator"].queryset = operators

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("'From' must be on or before 'To'.")
        return data


@staff_only
def reports(request):
    user = request.user
    allowed = scope(user)
    today = timezone.localdate()
    # Default: the last 30 days of sales and the next 30 days of sailings.
    form = ReportForm(request.GET or {"start": today - timedelta(days=30), "end": today + timedelta(days=30)}, operators=allowed)
    if not form.is_valid():
        return render(request, "staff/reports.html", {"form": form})
    start, end = form.cleaned_data["start"], form.cleaned_data["end"]
    ops = allowed.filter(pk=form.cleaned_data["operator"].pk) if form.cleaned_data["operator"] else allowed

    bookings = Booking.objects.filter(schedule__route__operator__in=ops, created_at__date__gte=start, created_at__date__lte=end)
    by_status = list(bookings.values("status").annotate(n=Count("id"), pax=Coalesce(Sum("passenger_count"), ZERO)).order_by("status"))
    labels = dict(Booking.Status.choices)
    for row in by_status:
        row["label"] = labels.get(row["status"], row["status"])
    sailings = with_occupancy(Schedule.objects.filter(
        route__operator__in=ops, departure_at__date__gte=start, departure_at__date__lte=end,
    ).exclude(status__in=Schedule.EDITABLE)).order_by("departure_at")[:300]
    cancellations = CancellationRequest.objects.filter(
        booking__schedule__route__operator__in=ops, created_at__date__gte=start, created_at__date__lte=end,
    ).values("status").annotate(n=Count("id")).order_by("status")

    money = None
    if sees_money(user):
        captured = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.CAPTURED, booking__schedule__route__operator__in=ops,
            captured_at__date__gte=start, captured_at__date__lte=end,
        ).aggregate(t=Coalesce(Sum("amount"), ZERO_MONEY), n=Count("id"))
        refunded = Refund.objects.filter(
            status=Refund.Status.SUCCEEDED, payment__booking__schedule__route__operator__in=ops,
            updated_at__date__gte=start, updated_at__date__lte=end,
        ).aggregate(t=Coalesce(Sum("amount"), ZERO_MONEY))["t"]
        money = {"captured": captured["t"], "payments": captured["n"], "refunded": refunded, "net": captured["t"] - refunded}

    if request.GET.get("format") == "csv":
        AuditLog.record(user, "report.exported", user, {"start": str(start), "end": str(end)}, request)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="sailings-{start}-{end}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Departure", "Route", "Vessel", "Status", "Places sold or held", "Capacity", "Occupancy %"])
        for s in sailings:
            writer.writerow([timezone.localtime(s.departure_at).strftime("%Y-%m-%d %H:%M"), str(s.route), s.vessel.name,
                             s.get_status_display(), s.sold, s.capacity, round(100 * s.sold / s.capacity) if s.capacity else 0])
        return response

    total_sold = sum(s.sold for s in sailings)
    total_capacity = sum(s.capacity for s in sailings)
    return render(request, "staff/reports.html", {
        "form": form, "by_status": by_status, "sailings": sailings, "cancellations": cancellations, "money": money,
        "occupancy": round(100 * total_sold / total_capacity) if total_capacity else 0,
        "query": request.GET.urlencode() or f"start={start}&end={end}",
    })


@support_only
def support_list(request):
    tickets = SupportTicket.objects.select_related("assigned_to").order_by("-updated_at")
    status = request.GET.get("status", "active")
    if status == "active":
        tickets = tickets.exclude(status__in=[SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED])
    elif status in SupportTicket.Status.values:
        tickets = tickets.filter(status=status)
    if request.GET.get("category") in SupportTicket.Category.values:
        tickets = tickets.filter(category=request.GET["category"])
    if q := request.GET.get("q", "").strip():
        tickets = tickets.filter(Q(reference__iexact=q) | Q(contact_email__icontains=q) | Q(subject__icontains=q))
    if request.GET.get("mine"):
        tickets = tickets.filter(assigned_to=request.user)
    page = Paginator(tickets, 25).get_page(request.GET.get("page"))
    return render(request, "staff/support_list.html", {
        "page": page, "status": status, "statuses": SupportTicket.Status.choices, "categories": SupportTicket.Category.choices,
    })


class StaffReplyForm(forms.Form):
    body = forms.CharField(label="Reply to the customer", widget=forms.Textarea(attrs={"rows": 5}), max_length=5000, required=False)
    status = forms.ChoiceField(label="Status", choices=SupportTicket.Status.choices)


@support_only
def support_detail(request, reference):
    ticket = get_object_or_404(SupportTicket.objects.select_related("booking", "user", "assigned_to"), reference=reference)
    form = StaffReplyForm(request.POST or None, initial={"status": SupportTicket.Status.AWAITING_CUSTOMER}, label_suffix="")
    if request.method == "POST":
        if "assign" in request.POST:
            ticket.assigned_to = request.user
            ticket.save(update_fields=["assigned_to", "updated_at"])
            AuditLog.record(request.user, "support.assigned", ticket, {}, request)
            return redirect("staff:support_detail", reference=reference)
        if form.is_valid():
            body, status = form.cleaned_data["body"].strip(), form.cleaned_data["status"]
            if body:
                SupportMessage.objects.create(ticket=ticket, author=request.user, is_staff_reply=True, body=body)
                notify_support(ticket, f"Reply to your request {ticket.reference}", body)
            old = ticket.status
            ticket.status = status
            ticket.resolved_at = timezone.now() if status in (SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED) else None
            ticket.save(update_fields=["status", "resolved_at", "updated_at"])
            AuditLog.record(request.user, "support.updated", ticket, {"status": [old, status], "replied": bool(body)}, request)
            messages.success(request, "Reply sent." if body else "Ticket updated.")
            return redirect("staff:support_detail", reference=reference)
    return render(request, "staff/support_detail.html", {
        "ticket": ticket, "thread": ticket.messages.select_related("author"), "form": form,
    })
