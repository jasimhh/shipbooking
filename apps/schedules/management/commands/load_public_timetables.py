"""Load real Kochi Water Metro services from public sources (not from the operator).

Sources, checked October 2026:
- Routes and distances, 100-passenger electric boats, average speed 8 knots, fares Rs 20-40:
  https://en.wikipedia.org/wiki/Kochi_Water_Metro
- High Court-Vypin fare Rs 20 and Vyttila-Kakkanad fare Rs 30 (launch fares, April 2023):
  https://www.thenewsminute.com/kerala/india-s-first-water-metro-becomes-operational-kochi-176355
- High Court-Vypin 08:40-20:10 every 25-35 minutes, about 16-20 minutes per crossing:
  https://www.thecurrentindia.com/tourism/kochi-water-metro-in-kerala/
- Service hours 7 am-8 pm (first phase, 2023): Wikipedia, as above.

Exact departure times are not published in a form we could verify, so sailings are spaced every 30 minutes
inside the published hours and every page says so. Terminal coordinates are approximate.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.fleet.models import CabinClass, Port, Route, Vessel
from apps.operators.models import Operator
from apps.schedules.models import Fare, Schedule

NOTE = ("Routes, times and fares for Kochi Water Metro come from public sources (Wikipedia and news reports, 2023-2026), "
        "not from the operator, and Ship Booking is not an official partner. Departures are approximate: every 30 minutes "
        "within the published service hours. Check with Kochi Water Metro before you travel.")

TERMINALS = [  # code, name, latitude, longitude (approximate)
    ("KWM-HC", "High Court Water Metro Terminal", "9.985900", "76.277000"),
    ("KWM-VYP", "Vypin Water Metro Terminal", "9.970500", "76.244500"),
    ("KWM-VYT", "Vyttila Water Metro Terminal", "9.967700", "76.321500"),
    ("KWM-KKD", "Kakkanad Water Metro Terminal", "10.015700", "76.348000"),
]
SERVICES = [  # origin, destination, first, last, minutes, fare
    ("KWM-HC", "KWM-VYP", "08:40", "20:10", 20, "20"),
    ("KWM-VYP", "KWM-HC", "08:40", "20:10", 20, "20"),
    ("KWM-VYT", "KWM-KKD", "07:00", "19:30", 20, "30"),
    ("KWM-KKD", "KWM-VYT", "07:00", "19:30", 20, "30"),
]
EVERY = timedelta(minutes=30)
DAYS_AHEAD = 14
CAPACITY = 100


class Command(BaseCommand):
    help = "Load Kochi Water Metro terminals, routes and approximate sailings from public sources for the next 14 days."

    @transaction.atomic
    def handle(self, *args, **options):
        operator, _ = Operator.objects.update_or_create(
            name="Kochi Water Metro", defaults={"legal_name": "Kochi Water Metro Ltd", "public_source": NOTE, "is_demo": False})
        ports = {}
        for code, name, lat, lon in TERMINALS:
            ports[code], _ = Port.objects.update_or_create(code=code, defaults={
                "name": name, "city": "Kochi", "state": "Kerala", "latitude": Decimal(lat), "longitude": Decimal(lon)})
        boat, made = Vessel.objects.get_or_create(operator=operator, name="Electric boat (100 passengers)", defaults={
            "vessel_type": "Electric hybrid passenger boat", "seating_mode": Vessel.SeatingMode.CAPACITY,
            "facilities": "Air-conditioned cabin."})
        if made:
            CabinClass.objects.create(vessel=boat, code="STD", name="Standard", capacity=CAPACITY)
        cabin = boat.cabin_classes.get(code="STD")

        today, created = timezone.localdate(), 0
        for origin, dest, first, last, minutes, fare in SERVICES:
            route, _ = Route.objects.get_or_create(operator=operator, origin=ports[origin], destination=ports[dest])
            for day in range(DAYS_AHEAD):
                date = today + timedelta(days=day)
                dep = timezone.make_aware(datetime.combine(date, time.fromisoformat(first)))
                end = timezone.make_aware(datetime.combine(date, time.fromisoformat(last)))
                while dep <= end:
                    schedule, new = Schedule.objects.get_or_create(route=route, vessel=boat, departure_at=dep, defaults={
                        "arrival_at": dep + timedelta(minutes=minutes), "status": Schedule.Status.PUBLISHED})
                    if new:
                        Fare.objects.create(schedule=schedule, cabin_class=cabin, base_fare=Decimal(fare),
                                            tax_amount=Decimal("0"), fee_amount=Decimal("0"), capacity=CAPACITY)
                        created += 1
                    dep += EVERY
        self.stdout.write(self.style.SUCCESS(f"Kochi Water Metro loaded: {created} new sailings over {DAYS_AHEAD} days."))
