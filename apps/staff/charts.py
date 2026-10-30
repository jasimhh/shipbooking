"""Harbour map: regions, port placement and estimated ferry state.

Ferries don't report positions, so a sailing's place on the map is estimated from its
timetable (departure and arrival times) and its status. The page labels it as estimated.

Two regions have hand-drawn, not-to-scale coastline art. Ports there are placed with a
linear projection anchored on two known jetties so they line up with the drawing. Any other
region is drawn on the bare grid with ports fitted to their coordinates.
"""

from datetime import timedelta

from django.utils import timezone
from django.utils.text import slugify

from apps.schedules.models import Schedule

VIEW_W, VIEW_H = 1000, 600
BOARDING_WINDOW = timedelta(minutes=30)

# (latitude, longitude) -> (x, y) anchors chosen so real coordinates land on the drawn jetties.
ART = {
    "maharashtra": {
        "label": "Mumbai harbour",
        "anchors": (((18.958, 72.846), (300, 362)), ((18.806, 72.882), (690, 452))),
        "land": [
            "M210 0 L330 0 L338 40 L326 72 L344 96 L336 128 L352 156 L340 190 L356 222 L344 258 L330 290 L318 326 L300 360 L288 392 L270 420 L256 446 L240 470 L226 486 L214 478 L222 452 L208 430 L214 404 L200 380 L206 352 L192 326 L198 296 L186 268 L192 236 L178 204 L186 172 L174 140 L184 108 L172 76 L186 44Z",
            "M640 0 L1000 0 L1000 600 L790 600 L770 572 L748 560 L742 528 L716 512 L712 482 L690 462 L700 432 L676 416 L668 388 L688 366 L672 340 L678 310 L660 290 L672 262 L652 238 L664 210 L644 186 L656 158 L636 134 L648 106 L630 80 L642 50Z",
            "M470 250 L500 236 L528 246 L540 272 L528 298 L500 308 L476 296 L464 272Z",
        ],
        "places": [["Mumbai", 210, 140], ["Raigad", 800, 300], ["Elephanta", 468, 232], ["Thane Creek", 420, 60]],
        "depths": [[420, 330, "6"], [520, 380, "9"], [600, 420, "11"], [380, 450, "7"], [560, 520, "14"], [460, 170, "4"]],
        "lights": [[238, 492]],
    },
    "andaman-and-nicobar-islands": {
        "label": "Andaman Islands",
        "anchors": (((11.672, 92.737), (334, 340)), ((12.035, 92.982), (664, 176))),
        "land": [
            "M150 120 L188 100 L226 108 L254 96 L286 118 L300 150 L320 168 L314 196 L334 222 L326 252 L342 280 L328 300 L300 302 L316 326 L338 340 L330 372 L310 396 L296 430 L276 466 L252 498 L222 526 L190 540 L164 520 L150 488 L136 452 L130 414 L118 378 L124 340 L110 302 L120 264 L108 226 L122 190 L116 154Z",
            "M352 316 L366 308 L378 318 L372 332 L356 332Z",
            "M640 70 L676 56 L712 64 L744 58 L772 84 L796 108 L790 140 L806 168 L792 196 L770 214 L748 240 L718 256 L690 244 L664 222 L648 196 L632 170 L620 140 L628 104Z",
        ],
        "places": [["South Andaman", 128, 240], ["Swaraj Dweep", 660, 44], ["Ross Island", 350, 300]],
        "depths": [[430, 280, "18"], [520, 240, "25"], [470, 380, "21"], [560, 170, "30"], [400, 200, "12"], [700, 330, "28"]],
        "lights": [[362, 318], [796, 108]],
    },
}


def region_key(port):
    return slugify(port.state) or "other"


def _projector(key, ports):
    art = ART.get(key)
    if art:
        ((lat1, lon1), (x1, y1)), ((lat2, lon2), (x2, y2)) = art["anchors"]
        kx, ky = (x2 - x1) / (lon2 - lon1), (y2 - y1) / (lat2 - lat1)
        return lambda lat, lon: (x1 + (lon - lon1) * kx, y1 + (lat - lat1) * ky)
    located = [p for p in ports if p.latitude is not None and p.longitude is not None]
    if not located:
        return None
    lats = [float(p.latitude) for p in located]
    lons = [float(p.longitude) for p in located]
    span_lat, span_lon = (max(lats) - min(lats)) or 1, (max(lons) - min(lons)) or 1
    pad = 140
    return lambda lat, lon: (
        pad + (lon - min(lons)) / span_lon * (VIEW_W - 2 * pad),
        pad + (max(lats) - lat) / span_lat * (VIEW_H - 2 * pad),
    )


def place_ports(key, ports):
    """Map position for every port in a region. Ports without coordinates are spread along the bottom."""
    project = _projector(key, ports)
    placed, missing = {}, []
    for p in ports:
        if project and p.latitude is not None and p.longitude is not None:
            x, y = project(float(p.latitude), float(p.longitude))
            placed[p.pk] = (round(x), round(y))
        else:
            missing.append(p)
    for i, p in enumerate(missing):
        placed[p.pk] = (160 + i * 180, VIEW_H - 120)
    return placed


def route_path(a, b):
    """A gentle curve from a to b, bowed to one side so routes don't look like rulers."""
    (x1, y1), (x2, y2) = a, b
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * 0.18, my + dx * 0.18
    return f"M{x1} {y1} Q{cx:.0f} {cy:.0f} {x2} {y2}"


def sailing_state(schedule, now=None):
    """(state, progress 0-1). States: cancelled, arrived, at_sea, boarding, scheduled."""
    now = now or timezone.now()
    if schedule.status == Schedule.Status.CANCELLED:
        return "cancelled", 0.0
    if now >= schedule.arrival_at:
        return "arrived", 1.0
    if now >= schedule.departure_at:
        total = (schedule.arrival_at - schedule.departure_at).total_seconds()
        return "at_sea", min(1.0, (now - schedule.departure_at).total_seconds() / total)
    if schedule.departure_at - now <= BOARDING_WINDOW:
        return "boarding", 0.0
    return "scheduled", 0.0


def dms(value, pos, neg):
    """18.958 -> 18°57′N"""
    v = float(value)
    deg = int(abs(v))
    minutes = round((abs(v) - deg) * 60)
    if minutes == 60:
        deg, minutes = deg + 1, 0
    return f"{deg}°{minutes:02d}′{pos if v >= 0 else neg}"
