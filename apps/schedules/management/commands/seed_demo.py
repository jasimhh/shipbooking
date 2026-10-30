"""Create clearly fictional demo data for development. Safe to run more than once.

Ports are real Indian passenger jetties. The operator, vessels, timings and
fares are invented and hang off an operator with is_demo=True, so the site
labels every sailing as demo data.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.fleet.models import CabinClass, Port, Route, Seat, Vessel
from apps.operators.models import Operator
from apps.schedules.models import Fare, Schedule

PORTS = [
    ("MUMFW", "Mumbai Ferry Wharf", "Mumbai", "Maharashtra", "18.958", "72.846"),
    ("MDWJ", "Mandwa Jetty", "Alibag", "Maharashtra", "18.806", "72.882"),
    ("PBPBJ", "Phoenix Bay Jetty", "Sri Vijaya Puram (Port Blair)", "Andaman and Nicobar Islands", "11.672", "92.737"),
    ("HVLJ", "Swaraj Dweep (Havelock) Jetty", "Swaraj Dweep", "Andaman and Nicobar Islands", "12.035", "92.982"),
]
# (origin, destination, departure times, journey minutes)
ROUTES = [
    ("MUMFW", "MDWJ", ["07:00", "11:30", "18:15"], 60),
    ("MDWJ", "MUMFW", ["08:30", "14:00", "19:45"], 60),
    ("PBPBJ", "HVLJ", ["06:30", "13:00"], 150),
    ("HVLJ", "PBPBJ", ["09:30", "16:00"], 150),
]
# (class code, name, capacity, base fare, tax, fee, rules)
CLASSES = {
    "capacity": [
        ("DECK", "Deck", 120, "450.00", "22.50", "15.00", "Demo fare rules: unreserved deck space."),
        ("SEAT", "Reserved seater", 60, "780.00", "39.00", "15.00", "Demo fare rules: reserved seating area."),
    ],
    "assigned": [
        ("CAB", "Cabin seat", 24, "1450.00", "72.50", "25.00", "Demo fare rules: numbered seat in an enclosed cabin."),
    ],
}
DAYS_AHEAD = 14


class Command(BaseCommand):
    help = "Create fictional demo operator, ports, vessels and sailings for the next 14 days."

    @transaction.atomic
    def handle(self, *args, **options):
        operator, _ = Operator.objects.get_or_create(
            name="Demo Ferries (fictional)",
            defaults={"is_demo": True, "verification_status": Operator.Verification.VERIFIED},
        )
        ports = {}
        # Real ports: no boarding instructions until an operator supplies verified ones.
        for code, name, city, state, lat, lon in PORTS:
            ports[code], _ = Port.objects.get_or_create(code=code, defaults={
                "name": name, "city": city, "state": state, "latitude": Decimal(lat), "longitude": Decimal(lon)})
        vessels = []
        for name, mode in [("MV Demo Star", "capacity"), ("MV Demo Wave", "assigned")]:
            vessel, created = Vessel.objects.get_or_create(
                operator=operator, name=name,
                defaults={"seating_mode": mode, "vessel_type": "Passenger ferry (demo)",
                          "facilities": "Demo facilities: seating, drinking water, toilets."},
            )
            if created:
                for code, cname, capacity, *_ in CLASSES[mode]:
                    cabin = CabinClass.objects.create(vessel=vessel, code=code, name=cname, capacity=capacity)
                    if mode == "assigned":
                        Seat.objects.bulk_create(Seat(cabin_class=cabin, number=f"{n:02d}") for n in range(1, capacity + 1))
            vessels.append(vessel)

        today = timezone.localdate()
        created = 0
        for i, (o, d, departures, minutes) in enumerate(ROUTES):
            route, _ = Route.objects.get_or_create(operator=operator, origin=ports[o], destination=ports[d])
            for day in range(DAYS_AHEAD):
                for j, hhmm in enumerate(departures):
                    vessel = vessels[(i + j) % len(vessels)]
                    dep = timezone.make_aware(datetime.combine(today + timedelta(days=day), time.fromisoformat(hhmm)))
                    schedule, made = Schedule.objects.get_or_create(
                        route=route, vessel=vessel, departure_at=dep,
                        defaults={"arrival_at": dep + timedelta(minutes=minutes), "status": Schedule.Status.PUBLISHED},
                    )
                    if not made:
                        continue
                    created += 1
                    for code, _, capacity, base, tax, fee, rules in CLASSES[vessel.seating_mode]:
                        Fare.objects.create(
                            schedule=schedule, cabin_class=vessel.cabin_classes.get(code=code),
                            base_fare=Decimal(base), tax_amount=Decimal(tax), fee_amount=Decimal(fee),
                            fare_rules=rules, capacity=capacity,
                        )
        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({created} new sailings). Ports are real; operator, vessels, timings and fares are fictional."))
