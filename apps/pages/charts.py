"""Passenger-facing route maps, drawn with the same chart art and projection as the staff Harbour Master map."""
from apps.fleet.models import Port
from apps.staff import charts


def _chart(key, routes, highlight=None):
    ports = {p.pk: p for r in routes for p in (r.origin, r.destination)}
    # All active ports in the area, so the map has context even with one route.
    for p in Port.objects.filter(is_active=True):
        if charts.region_key(p) == key:
            ports.setdefault(p.pk, p)
    pos = charts.place_ports(key, list(ports.values()))
    art = charts.ART.get(key)
    return {
        "key": key,
        "label": art["label"] if art else (next(iter(ports.values())).state or "Other"),
        "art": art,
        "ports": [{"name": p.name, "x": x, "y": y, "left": x > 720, "coord": f'{charts.dms(p.latitude, "N", "S")} {charts.dms(p.longitude, "E", "W")}' if p.latitude is not None else ""}
                  for p in ports.values() for x, y in [pos[p.pk]]],
        "routes": [{"route": r, "path": charts.route_path(pos[r.origin_id], pos[r.destination_id]),
                    "on": highlight is None or r.pk == highlight} for r in routes],
    }


def area_charts(route_cards):
    """One chart per area for the home page, each listing its routes (with next sailing and lowest fare)."""
    areas = {}
    for card in route_cards:
        areas.setdefault(charts.region_key(card["route"].origin), []).append(card)
    result = []
    for key, cards in areas.items():
        chart = _chart(key, [c["route"] for c in cards])
        for line, card in zip(chart["routes"], cards):
            line["card"] = card
        result.append(chart)
    return result


def sailing_chart(schedule):
    """Map of a sailing's area with its route highlighted and the ferry's estimated position."""
    route = schedule.route
    chart = _chart(charts.region_key(route.origin), [route], highlight=route.pk)
    chart["sailing"] = schedule
    return chart


def journey_regions():
    """Every area with active ports, for the search form's journey preview map."""
    areas = {}
    for p in Port.objects.filter(is_active=True):
        areas.setdefault(charts.region_key(p), []).append(p)
    result = []
    for key, ports in areas.items():
        pos = charts.place_ports(key, ports)
        art = charts.ART.get(key)
        result.append({
            "key": key, "label": art["label"] if art else (ports[0].state or "Other"), "art": art,
            "ports": [{"code": p.code, "name": p.name, "x": pos[p.pk][0], "y": pos[p.pk][1], "left": pos[p.pk][0] > 720} for p in ports],
        })
    return result
