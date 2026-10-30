"""Load real ferry services from public sources (not from the operators). Sailings are timetable-only.

Sources, checked October 2026:
Kochi Water Metro
- Routes, distances, 100-passenger electric boats, fares Rs 20-40, hours 7 am-8 pm:
  https://en.wikipedia.org/wiki/Kochi_Water_Metro
- High Court-Vypin Rs 20, Vyttila-Kakkanad Rs 30 (launch fares, April 2023):
  https://www.thenewsminute.com/kerala/india-s-first-water-metro-becomes-operational-kochi-176355
- High Court-Vypin 08:40-20:10 every 25-35 min, 16-20 min crossing:
  https://www.thecurrentindia.com/tourism/kochi-water-metro-in-kerala/
M2M Ferries (Mumbai Ferry Wharf - Mandwa Ro-Pax)
- Route since 2018, Ferry Wharf (Bhaucha Dhakka) to Mandwa: https://en.wikipedia.org/wiki/RORO_ferries_in_India
- 3 sailings a day, adult fare Rs 420 (Rome2Rio listing); about an hour, 500 passengers (travel blog, 2020):
  https://myyatradiary.com/2020/12/m2m-ferries-best-ride-mumbai-alibag-details-experience.html
Makruzz (Port Blair Haddo Wharf - Swaraj Dweep)
- Departs Haddo Wharf; Rs 1,200-2,500 one way; 90 min-2 h:
  https://blog.makruzz.com/port-blair-to-havelock-ferry-guide-2026/
- Port Blair departures 06:00, 08:00 (arr 09:30), 12:00, 16:00 (16 May-23 Jun 2026 schedule): Makruzz blog, as above.

Where exact times aren't published they are spaced inside the published hours and every page says they are approximate.
Terminal coordinates are approximate.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.fleet.models import CabinClass, Port, Route, Vessel
from apps.operators.models import Operator
from apps.schedules.models import Fare, Schedule

DAYS_AHEAD = 14


def every(first, last, minutes):
    out, t = [], datetime.combine(datetime.today(), time.fromisoformat(first))
    end = datetime.combine(datetime.today(), time.fromisoformat(last))
    while t <= end:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=minutes)
    return out


OPERATORS = [
    {
        "name": "Kochi Water Metro", "legal_name": "Kochi Water Metro Ltd",
        "note": ("Routes, times and fares for Kochi Water Metro come from public sources (Wikipedia and news reports, 2023-2026), "
                 "not from the operator, and Ship Booking is not an official partner. Departures are approximate: every 30 minutes "
                 "within the published service hours. Check with Kochi Water Metro before you travel."),
        "terminals": [("KWM-HC", "High Court Water Metro Terminal", "Kochi", "Kerala", "9.985900", "76.277000"),
                      ("KWM-VYP", "Vypin Water Metro Terminal", "Kochi", "Kerala", "9.970500", "76.244500"),
                      ("KWM-VYT", "Vyttila Water Metro Terminal", "Kochi", "Kerala", "9.967700", "76.321500"),
                      ("KWM-KKD", "Kakkanad Water Metro Terminal", "Kochi", "Kerala", "10.015700", "76.348000")],
        "vessel": ("Electric boat (100 passengers)", "Electric hybrid passenger boat", "Air-conditioned cabin."),
        "classes": [("STD", "Standard", 100)],
        "services": [("KWM-HC", "KWM-VYP", every("08:40", "20:10", 30), 20, {"STD": "20"}),
                     ("KWM-VYP", "KWM-HC", every("08:40", "20:10", 30), 20, {"STD": "20"}),
                     ("KWM-VYT", "KWM-KKD", every("07:00", "19:30", 30), 20, {"STD": "30"}),
                     ("KWM-KKD", "KWM-VYT", every("07:00", "19:30", 30), 20, {"STD": "30"})],
    },
    {
        "name": "M2M Ferries", "legal_name": "",
        "note": ("M2M Ferries' Ro-Pax service between Mumbai Ferry Wharf (Bhaucha Dhakka) and Mandwa is shown from public sources "
                 "(Wikipedia, Rome2Rio and travel reports): about 3 sailings a day, about an hour, adult fare Rs 420. Exact departure "
                 "times are not published there, so the times shown are approximate. Ship Booking is not an official partner; "
                 "check with M2M Ferries before you travel."),
        "terminals": [("MUMFW", "Mumbai Ferry Wharf", "Mumbai", "Maharashtra", "18.958000", "72.846000"),
                      ("MDWJ", "Mandwa Jetty", "Alibag", "Maharashtra", "18.806000", "72.882000")],
        "vessel": ("Ro-Pax ferry (500 passengers)", "Ro-Pax (passengers and vehicles)", "Passenger lounge; carries cars and bikes."),
        "classes": [("ADT", "Adult", 500)],
        "services": [("MUMFW", "MDWJ", ["09:00", "13:00", "17:00"], 60, {"ADT": "420"}),
                     ("MDWJ", "MUMFW", ["10:30", "14:30", "18:30"], 60, {"ADT": "420"})],
    },
    {
        "name": "Makruzz", "legal_name": "",
        "note": ("Makruzz sailings between Port Blair (Haddo Wharf) and Swaraj Dweep come from the operator's public blog "
                 "(2026 schedule): departures from Port Blair at 06:00, 08:00, 12:00 and 16:00, about 90 minutes, fares from "
                 "Rs 1,200 (published range Rs 1,200-2,500). Return times are not published there and are approximate. "
                 "Ship Booking is not an official partner; check with Makruzz before you travel."),
        "terminals": [("PBHDW", "Haddo Wharf (Port Blair)", "Sri Vijaya Puram", "Andaman and Nicobar Islands", "11.677500", "92.725500"),
                      ("HVLJ", "Swaraj Dweep (Havelock) Jetty", "Swaraj Dweep", "Andaman and Nicobar Islands", "12.035000", "92.982000")],
        "vessel": ("Makruzz high-speed catamaran", "High-speed passenger catamaran", "Air-conditioned seating."),
        "classes": [("PRM", "Premium", 200)],
        "services": [("PBHDW", "HVLJ", ["06:00", "08:00", "12:00", "16:00"], 90, {"PRM": "1200"}),
                     ("HVLJ", "PBHDW", ["08:00", "10:00", "14:00", "18:00"], 90, {"PRM": "1200"})],
    },
]


class Command(BaseCommand):
    help = "Load public-source ferry services (Kochi Water Metro, M2M Ferries, Makruzz) for the next 14 days, timetable-only."

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        for spec in OPERATORS:
            operator, _ = Operator.objects.update_or_create(name=spec["name"], defaults={
                "legal_name": spec["legal_name"], "public_source": spec["note"], "is_demo": False})
            for code, name, city, state, lat, lon in spec["terminals"]:
                Port.objects.get_or_create(code=code, defaults={
                    "name": name, "city": city, "state": state, "latitude": Decimal(lat), "longitude": Decimal(lon)})
            vname, vtype, facilities = spec["vessel"]
            boat, made = Vessel.objects.get_or_create(operator=operator, name=vname, defaults={
                "vessel_type": vtype, "seating_mode": Vessel.SeatingMode.CAPACITY, "facilities": facilities})
            if made:
                for code, cname, capacity in spec["classes"]:
                    CabinClass.objects.create(vessel=boat, code=code, name=cname, capacity=capacity)
            cabins = {c.code: c for c in boat.cabin_classes.all()}
            created = 0
            for origin, dest, departures, minutes, fares in spec["services"]:
                route, _ = Route.objects.get_or_create(
                    operator=operator, origin=Port.objects.get(code=origin), destination=Port.objects.get(code=dest))
                for day in range(DAYS_AHEAD):
                    for hhmm in departures:
                        dep = timezone.make_aware(datetime.combine(today + timedelta(days=day), time.fromisoformat(hhmm)))
                        schedule, new = Schedule.objects.get_or_create(route=route, vessel=boat, departure_at=dep, defaults={
                            "arrival_at": dep + timedelta(minutes=minutes), "status": Schedule.Status.PUBLISHED})
                        if not new:
                            continue
                        created += 1
                        for code, price in fares.items():
                            Fare.objects.create(schedule=schedule, cabin_class=cabins[code], base_fare=Decimal(price),
                                                tax_amount=Decimal("0"), fee_amount=Decimal("0"), capacity=cabins[code].capacity)
            self.stdout.write(f"{operator.name}: {created} new sailings")
