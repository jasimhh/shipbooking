from datetime import timedelta

from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Min
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.compliance.models import PolicyVersion
from apps.fleet.models import Route
from apps.schedules.models import Fare, Schedule
from apps.support.models import SupportMessage, SupportTicket

from .forms import ContactForm, SearchForm
from .models import FAQ, Announcement, ContentPage

SORTS = {
    "departure": ("Earliest departure", lambda r: r["schedule"].departure_at),
    "price": ("Lowest fare", lambda r: r["from_price"]),
    "duration": ("Shortest journey", lambda r: r["schedule"].duration),
}
TIME_WINDOWS = {
    "morning": ("Morning (before 12:00)", 0, 12),
    "afternoon": ("Afternoon (12:00–17:00)", 12, 17),
    "evening": ("Evening (after 17:00)", 17, 24),
}
CONTACT_LIMIT_PER_HOUR = 5


def guides():
    return ContentPage.objects.filter(section=ContentPage.Section.GUIDE, is_published=True)


def route_cards():
    """Next bookable sailing and lowest current fare for each active route."""
    cards = []
    # ponytail: two queries per route; fine for a handful of routes, aggregate in one query if there are dozens.
    for route in Route.objects.filter(is_active=True).select_related("operator", "origin", "destination"):
        sailings = Schedule.objects.bookable().filter(route=route)
        upcoming = sailings.select_related("vessel").order_by("departure_at").first()
        if not upcoming:
            continue
        from_price = Fare.objects.filter(schedule__in=sailings).aggregate(
            p=Min(F("base_fare") + F("tax_amount") + F("fee_amount"))
        )["p"]
        cards.append({"route": route, "next": upcoming, "from_price": from_price})
    return cards


def home(request):
    return render(request, "pages/home.html", {
        "form": SearchForm(initial={"date": timezone.localdate(), "passengers": 1}),
        "announcements": Announcement.objects.current(),
        "routes": route_cards(),
    })


def search(request):
    if not request.GET:
        return redirect("pages:home")
    form = SearchForm(request.GET)
    if not form.is_valid():
        return render(request, "pages/search.html", {"form": form})

    origin, destination = form.cleaned_data["origin"], form.cleaned_data["destination"]
    date, passengers = form.cleaned_data["date"], form.cleaned_data["passengers"]
    sort = request.GET.get("sort") if request.GET.get("sort") in SORTS else "departure"
    time = request.GET.get("time") if request.GET.get("time") in TIME_WINDOWS else ""

    on_route = Schedule.objects.bookable().filter(route__origin=origin, route__destination=destination)
    sailings = (
        on_route.filter(departure_at__date=date)
        .select_related("route__operator", "route__origin", "route__destination", "vessel")
        .prefetch_related("fares__cabin_class")
    )
    # ponytail: filtered and sorted in Python; fine for the handful of sailings per route per day.
    results = []
    for schedule in sailings:
        fares = list(schedule.fares.all())
        if not fares:
            continue
        if time:
            _, start, end = TIME_WINDOWS[time]
            if not start <= timezone.localtime(schedule.departure_at).hour < end:
                continue
        open_fares = [f for f in fares if f.available >= passengers]
        results.append({
            "schedule": schedule,
            "from_price": min(f.unit_total for f in (open_fares or fares)),
            "available": sum(f.available for f in fares),
            "bookable": bool(open_fares),
        })
    results.sort(key=SORTS[sort][1])

    other_dates = []
    if not results:
        other_dates = [d.date() for d in on_route.filter(departure_at__date__gt=date).datetimes("departure_at", "day")[:3]]

    return render(request, "pages/search.html", {
        "form": form,
        "results": results,
        "origin": origin,
        "destination": destination,
        "date": date,
        "passengers": passengers,
        "sort": sort,
        "sorts": {k: v[0] for k, v in SORTS.items()},
        "time": time,
        "time_windows": {k: v[0] for k, v in TIME_WINDOWS.items()},
        "other_dates": other_dates,
    })


def sailing_detail(request, pk):
    schedule = get_object_or_404(
        Schedule.objects.public().select_related(
            "route__operator", "route__origin", "route__destination", "vessel"
        ),
        pk=pk,
    )
    return render(request, "pages/sailing_detail.html", {
        "schedule": schedule,
        "fares": schedule.fares.select_related("cabin_class").order_by("base_fare"),
        "is_bookable": Schedule.objects.bookable().filter(pk=pk).exists(),
        "search_query": request.GET.urlencode(),
    })


def help_centre(request):
    return render(request, "pages/help.html", {"guides": guides()})


def content_page(request, slug, section=ContentPage.Section.GUIDE):
    page = get_object_or_404(ContentPage, slug=slug, section=section, is_published=True)
    return render(request, "pages/content_page.html", {"page": page, "guides": guides()})


def faq(request):
    return render(request, "pages/faq.html", {"faqs": FAQ.objects.filter(is_published=True)})


def service_updates(request):
    now = timezone.now()
    changed = (
        Schedule.objects.filter(
            status__in=[Schedule.Status.DELAYED, Schedule.Status.CANCELLED],
            departure_at__gte=now - timedelta(days=1),
            departure_at__lte=now + timedelta(days=14),
        )
        .select_related("route__origin", "route__destination", "vessel")
    )
    return render(request, "pages/service_updates.html", {
        "announcements": Announcement.objects.current(),
        "changed": changed,
    })


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["website"]:
            return redirect("pages:contact")  # bot; pretend success, store nothing
        # ponytail: per-IP limit in the local cache; behind Nginx set REMOTE_ADDR from the proxy (Phase 10).
        key = f"contact-rate:{request.META.get('REMOTE_ADDR', '')}"
        if cache.get_or_set(key, 0, 3600) >= CONTACT_LIMIT_PER_HOUR:
            messages.error(request, "Too many messages from your network. Please try again in an hour.")
            return render(request, "pages/contact.html", {"form": form}, status=429)
        cache.incr(key)

        data = form.cleaned_data
        body = data["message"]
        if data["booking_reference"]:
            body = f"Booking reference given: {data['booking_reference']}\n\n{body}"
        with transaction.atomic():
            ticket = SupportTicket.objects.create(
                user=request.user if request.user.is_authenticated else None,
                contact_email=data["email"],
                category=data["category"],
                subject=data["subject"],
            )
            SupportMessage.objects.create(
                ticket=ticket, author=ticket.user, body=body
            )
        messages.success(request, f"Message received. Your reference is {ticket.reference}.")
        return redirect("pages:contact")
    return render(request, "pages/contact.html", {"form": form})


def policy(request, policy_type):
    if policy_type not in PolicyVersion.PolicyType.values:
        raise Http404
    version = (
        PolicyVersion.objects.filter(policy_type=policy_type, is_published=True, effective_from__lte=timezone.now())
        .order_by("-effective_from")
        .first()
    )
    return render(request, "pages/policy.html", {
        "title": PolicyVersion.PolicyType(policy_type).label,
        "version": version,
    })
