"""Harbour master: live map of today's sailings, alerts, passengers and the fleet."""

import re
from datetime import datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import can_view_manifest
from apps.bookings.models import Booking, BookingPassenger, CancellationRequest
from apps.compliance.models import AuditLog, PrivacyRequest
from apps.fleet.models import CabinClass, Route, Vessel
from apps.operators.models import Operator
from apps.payments.models import PaymentTransaction, Refund
from apps.schedules.models import InventoryHold, Schedule
from apps.support.models import SupportTicket

from . import charts
from .views import scope, sees_money, staff_only, with_occupancy


def _is_support(user):
    return user.is_platform_admin or user.role == User.Role.SUPPORT


def _can_see_passengers(user, schedule):
    return _is_support(user) or can_view_manifest(user, schedule)


def _local(dt, fmt="%H:%M"):
    return timezone.localtime(dt).strftime(fmt)


@staff_only
def harbour(request):
    user, now = request.user, timezone.now()
    ops = scope(user)
    today = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(today, time.min))
    day_end = day_start + timedelta(days=1)

    routes = list(Route.objects.filter(operator__in=ops, is_active=True).select_related("origin", "destination"))
    sailings = list(with_occupancy(
        Schedule.objects.filter(route__in=routes, departure_at__lt=day_end, arrival_at__gte=day_start)
        .exclude(status__in=Schedule.EDITABLE)
    ).order_by("departure_at"))

    regions = {}
    for r in routes:
        key = charts.region_key(r.origin)
        region = regions.setdefault(key, {"key": key, "ports": {}, "routes": [], "sailings": []})
        region["ports"][r.origin.pk] = r.origin
        region["ports"][r.destination.pk] = r.destination
        region["routes"].append(r)

    data = []
    for key, region in regions.items():
        ports = list(region["ports"].values())
        pos = charts.place_ports(key, ports)
        art = charts.ART.get(key)
        route_ids = {r.pk for r in region["routes"]}
        region_sailings = []
        for s in sailings:
            if s.route_id not in route_ids:
                continue
            state, progress = charts.sailing_state(s, now)
            region_sailings.append({
                "id": s.pk, "time": _local(s.departure_at), "arrives": _local(s.arrival_at),
                "route": s.route_id, "label": f"{s.route.origin.name} → {s.route.destination.name}",
                "vessel": s.vessel.name, "sold": s.sold, "capacity": s.capacity,
                "state": state, "progress": round(progress, 4), "delayed": s.status == Schedule.Status.DELAYED,
                "note": s.status_note, "dep": s.departure_at.isoformat(), "arr": s.arrival_at.isoformat(),
                "passengers": reverse("staff:harbour_passengers", args=[s.pk]) if _can_see_passengers(user, s) else None,
            })
        data.append({
            "key": key,
            "label": art["label"] if art else (ports[0].state or "Other"),
            "art": {k: art[k] for k in ("land", "places", "depths", "lights")} if art else None,
            "ports": [{
                "id": p.pk, "name": p.name, "x": pos[p.pk][0], "y": pos[p.pk][1],
                "coord": f"{charts.dms(p.latitude, 'N', 'S')} {charts.dms(p.longitude, 'E', 'W')}" if p.latitude is not None else "Position not set",
            } for p in ports],
            "routes": [{"id": r.pk, "path": charts.route_path(pos[r.origin_id], pos[r.destination_id]),
                        "from": r.origin.name, "to": r.destination.name} for r in region["routes"]],
            "sailings": region_sailings,
        })
    data.sort(key=lambda r: r["label"])

    today_sailings = [s for s in sailings if s.departure_at >= day_start]
    confirmed = Booking.objects.filter(schedule__in=today_sailings, status=Booking.Status.CONFIRMED)
    stats = {
        "sailings": len(today_sailings),
        "delayed": sum(s.status == Schedule.Status.DELAYED for s in today_sailings),
        "cancelled": sum(s.status == Schedule.Status.CANCELLED for s in today_sailings),
        "passengers": confirmed.aggregate(n=Sum("passenger_count"))["n"] or 0,
    }
    if sees_money(user):
        stats["received"] = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.CAPTURED, captured_at__gte=day_start,
            booking__schedule__route__operator__in=ops,
        ).aggregate(t=Sum("amount"))["t"] or 0

    alerts = _alerts(user, ops, now, sailings)
    stats["issues"] = len(alerts)

    fleet = []
    for v in Vessel.objects.filter(operator__in=ops).select_related("operator").prefetch_related("cabin_classes").order_by("name"):
        fleet.append({"name": v.name, "operator": v.operator.name, "active": v.is_active,
                      "capacity": sum(c.capacity for c in v.cabin_classes.all()),
                      "seating": v.get_seating_mode_display()})

    return render(request, "staff/harbour.html", {
        "data": {"regions": data, "stats": stats, "alerts": alerts, "fleet": fleet,
                 "money": sees_money(user), "now": now.isoformat()},
        "can_add_ferry": user.is_platform_admin,
        "ferry_form": FerryForm() if user.is_platform_admin else None,
    })


def _alerts(user, ops, now, sailings):
    alerts = []
    for s in sailings:
        if s.status == Schedule.Status.DELAYED and s.arrival_at > now:
            alerts.append({"level": "warn", "icon": "clock", "title": f"{_local(s.departure_at)} {s.route.origin.name} → {s.route.destination.name} delayed",
                           "detail": s.status_note or "No note from the operator", "url": reverse("staff:manifest", args=[s.pk])})
        elif s.status == Schedule.Status.CANCELLED and s.departure_at > now - timedelta(hours=6):
            alerts.append({"level": "bad", "icon": "clock", "title": f"{_local(s.departure_at)} {s.route.origin.name} → {s.route.destination.name} cancelled",
                           "detail": s.status_note or "Bookings cancelled and refunds queued", "url": ""})
    for hold in (InventoryHold.objects.filter(status=InventoryHold.Status.ACTIVE, expires_at__lte=now + timedelta(minutes=10),
                                              fare__schedule__route__operator__in=ops).select_related("booking")[:5]):
        alerts.append({"level": "bad", "icon": "card", "title": f"Unpaid hold: {hold.booking.reference}",
                       "detail": f"{hold.quantity} place(s) released at {_local(hold.expires_at)} unless paid", "url": ""})
    if _is_support(user):
        urgent = SupportTicket.objects.filter(
            category__in=[SupportTicket.Category.GRIEVANCE, SupportTicket.Category.COMPLAINT], assigned_to__isnull=True,
        ).exclude(status__in=[SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED])
        for t in urgent[:5]:
            alerts.append({"level": "bad", "icon": "msg", "title": f"{t.get_category_display()} not assigned",
                           "detail": f"{t.reference} · {t.subject}", "url": reverse("staff:support_detail", args=[t.reference])})
        pending = CancellationRequest.objects.filter(status=CancellationRequest.Status.REQUESTED).count()
        if pending:
            alerts.append({"level": "warn", "icon": "ticket", "title": f"{pending} cancellation request(s) to decide",
                           "detail": "Approve or reject in the admin", "url": reverse("admin:bookings_cancellationrequest_changelist")})
    if user.is_platform_admin:
        refunds = Refund.objects.filter(status__in=[Refund.Status.PENDING, Refund.Status.FAILED])
        if refunds.exists():
            total = refunds.aggregate(t=Sum("amount"))["t"]
            alerts.append({"level": "warn", "icon": "card", "title": f"{refunds.count()} refund(s) to send",
                           "detail": f"Total ₹{total:,.2f}", "url": reverse("admin:payments_refund_changelist")})
        waiting = PrivacyRequest.objects.filter(status__in=[PrivacyRequest.Status.RECEIVED, PrivacyRequest.Status.IN_PROGRESS]).count()
        if waiting:
            alerts.append({"level": "warn", "icon": "msg", "title": f"{waiting} privacy request(s) open",
                           "detail": "Access, correction or deletion requests", "url": reverse("admin:compliance_privacyrequest_changelist")})
    return alerts[:20]


@staff_only
def harbour_passengers(request, pk):
    schedule = get_object_or_404(Schedule.objects.select_related("route__operator"), pk=pk)
    if not _can_see_passengers(request.user, schedule):
        raise PermissionDenied
    rows = []
    passengers = (BookingPassenger.objects
                  .filter(booking__schedule=schedule, booking__status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING])
                  .select_related("booking__hold", "seat__seat").prefetch_related("booking__tickets", "booking__payments")
                  .order_by("booking__status", "booking__reference", "id"))
    for p in passengers:
        b = p.booking
        ticket = next((t for t in b.tickets.all() if t.status != "void"), None)
        paid = next((t for t in b.payments.all() if t.status == PaymentTransaction.Status.CAPTURED), None)
        if b.status == Booking.Status.PENDING:
            hold = getattr(b, "hold", None)
            payment, state = (f"Unpaid · hold ends {_local(hold.expires_at)}" if hold else "Unpaid"), "bad"
        else:
            payment, state = (f"₹{paid.amount:,.2f} paid" if paid else "Confirmed"), "ok"
        seat = p.seat.seat.number if hasattr(p, "seat") and p.seat.active_schedule_id else ""
        rows.append({
            "name": p.full_name, "initials": "".join(w[0] for w in p.full_name.split()[:2]).upper(),
            "booking": b.reference, "age": p.age, "gender": p.get_gender_display(),
            "email": b.contact_email, "phone": b.contact_phone,
            "cabin": b.fare_snapshot.get("cabin_class", "") + (f" · seat {seat}" if seat else ""),
            "ticket": ticket.get_status_display() if ticket else ("Unpaid" if state == "bad" else "No ticket"),
            "state": "sea" if ticket and ticket.status == "boarded" else state,
            "payment": payment,
            "admin_url": reverse("admin:bookings_booking_change", args=[b.pk]) if request.user.is_platform_admin else "",
        })
    AuditLog.record(request.user, "harbour.passengers_viewed", schedule, {"count": len(rows)}, request)
    response = JsonResponse({"sailing": schedule.pk, "passengers": rows})
    response["Cache-Control"] = "private, no-store"
    return response


class FerryForm(forms.ModelForm):
    classes = forms.CharField(
        label="Classes and capacity", widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One class per line, for example “Deck · 120”.", initial="Deck · 120",
    )

    class Meta:
        model = Vessel
        fields = ["name", "operator", "imo_number", "vessel_type", "seating_mode"]
        labels = {"name": "Ferry name", "imo_number": "IMO number", "vessel_type": "Type"}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields["operator"].queryset = Operator.objects.filter(is_active=True)

    def clean_classes(self):
        parsed = []
        for line in self.cleaned_data["classes"].splitlines():
            if not line.strip():
                continue
            m = re.match(r"^\s*(.+?)\s*[·:,\-]?\s*(\d{1,5})\s*$", line)
            if not m or int(m.group(2)) < 1:
                raise forms.ValidationError(f"Couldn't read “{line.strip()}”. Use a name and a number, like “Deck · 120”.")
            parsed.append((m.group(1).strip(" ·:-,"), int(m.group(2))))
        if not parsed:
            raise forms.ValidationError("Add at least one class.")
        codes = [slugify(n).upper()[:20] or f"C{i}" for i, (n, _) in enumerate(parsed)]
        if len(set(codes)) != len(codes):
            raise forms.ValidationError("Each class needs a different name.")
        return list(zip(codes, parsed))


@staff_only
@require_POST
def add_ferry(request):
    if not request.user.is_platform_admin:
        raise PermissionDenied
    form = FerryForm(request.POST)
    if not form.is_valid():
        errors = "; ".join(f"{form.fields[f].label if f in form.fields else 'Form'}: {' '.join(e)}" for f, e in form.errors.items())
        messages.error(request, f"Ferry not added. {errors}")
        return redirect("staff:harbour")
    with transaction.atomic():
        vessel = form.save()
        CabinClass.objects.bulk_create(
            CabinClass(vessel=vessel, code=code, name=name, capacity=cap) for code, (name, cap) in form.cleaned_data["classes"]
        )
        AuditLog.record(request.user, "vessel.created", vessel, {
            "operator": vessel.operator.name, "classes": [f"{n} {c}" for _, (n, c) in form.cleaned_data["classes"]],
        }, request)
    messages.success(request, f"{vessel.name} added to the fleet. Add sailings for it in Sailings.")
    return redirect("staff:harbour")
