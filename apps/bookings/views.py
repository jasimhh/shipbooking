from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.compliance.models import PolicyVersion
from apps.schedules.models import Fare, Schedule

from . import services
from .forms import MAX_PASSENGERS, PassengerFormSet, TripForm
from .models import Booking, BookingPassenger

DRAFT_KEY = "booking_draft"


def _bookable_or_back(request, pk):
    """The sailing if it's open for booking, else a redirect explaining why not."""
    services.expire_holds()
    schedule = get_object_or_404(Schedule.objects.public().select_related("route__origin", "route__destination", "vessel"), pk=pk)
    if not Schedule.objects.bookable().filter(pk=pk).exists():
        messages.error(request, "This sailing isn't open for booking.")
        return schedule, redirect("pages:sailing", pk=pk)
    if not request.user.email_verified:
        messages.warning(request, "Please confirm your email address before booking. We can send you a new link.")
        return schedule, redirect("accounts:dashboard")
    return schedule, None


@login_required
def details(request, pk):
    schedule, stop = _bookable_or_back(request, pk)
    if stop:
        return stop
    try:
        count = min(max(int(request.GET.get("passengers", 1)), 1), MAX_PASSENGERS)
    except ValueError:
        count = 1

    user = request.user
    if request.method == "POST":
        trip = TripForm(request.POST, schedule=schedule)
        people = PassengerFormSet(request.POST, prefix="p")
        if trip.is_valid() and people.is_valid():
            fare = trip.cleaned_data["fare"]
            if fare.available < len(people.cleaned_data):
                trip.add_error("fare", f"Only {fare.available} place(s) left in this class.")
            else:
                request.session[DRAFT_KEY] = {
                    "schedule": schedule.pk,
                    "fare": fare.pk,
                    "contact_email": trip.cleaned_data["contact_email"],
                    "contact_phone": trip.cleaned_data["contact_phone"],
                    "passengers": people.cleaned_data,
                }
                return redirect("bookings:review", pk=schedule.pk)
    else:
        trip = TripForm(schedule=schedule, initial={
            "fare": request.GET.get("fare"), "contact_email": user.email, "contact_phone": user.phone,
        })
        people = PassengerFormSet(prefix="p", initial=[{"full_name": user.get_full_name()}] + [{}] * (count - 1))

    return render(request, "bookings/details.html", {"schedule": schedule, "trip": trip, "people": people})


@login_required
def review(request, pk):
    schedule, stop = _bookable_or_back(request, pk)
    if stop:
        return stop
    draft = request.session.get(DRAFT_KEY)
    if not draft or draft["schedule"] != schedule.pk:
        return redirect("bookings:details", pk=pk)
    fare = get_object_or_404(Fare.objects.select_related("cabin_class"), pk=draft["fare"], schedule=schedule)

    if request.method == "POST":
        try:
            booking = services.reserve(request.user, fare.pk, draft["passengers"], draft["contact_email"], draft["contact_phone"])
        except services.BookingError as e:
            messages.error(request, str(e))
            return redirect("bookings:details", pk=pk)
        del request.session[DRAFT_KEY]
        return redirect("bookings:detail", reference=booking.reference)

    passengers = [{**p, "gender_label": BookingPassenger.Gender(p["gender"]).label} for p in draft["passengers"]]
    return render(request, "bookings/review.html", {
        "schedule": schedule, "fare": fare, "draft": draft, "passengers": passengers,
        "amounts": services.price(fare, len(draft["passengers"])),
        "hold_minutes": settings.INVENTORY_HOLD_MINUTES,
        "cancellation_policy": PolicyVersion.objects.filter(policy_type="cancellation", is_published=True).order_by("-effective_from").first(),
    })


def _own_booking(request, reference):
    return get_object_or_404(
        Booking.objects.select_related("schedule__route__origin", "schedule__route__destination", "schedule__vessel", "fare__cabin_class", "hold"),
        reference=reference, user=request.user,
    )


@login_required
def detail(request, reference):
    services.expire_holds()
    booking = _own_booking(request, reference)
    return render(request, "bookings/detail.html", {
        "booking": booking,
        "passengers": booking.passengers.select_related("seat__seat"),
    })


@login_required
@require_POST
def cancel_reservation(request, reference):
    booking = _own_booking(request, reference)
    if booking.status == Booking.Status.PENDING and services.release(booking, Booking.Status.CANCELLED, "Cancelled by passenger before payment", request.user):
        messages.success(request, "Reservation cancelled and your places released.")
    else:
        messages.info(request, "This reservation can't be cancelled here.")
    return redirect("bookings:detail", reference=reference)
