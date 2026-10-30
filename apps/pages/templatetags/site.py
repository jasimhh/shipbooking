from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()


@register.filter
def inr(amount):
    """Format as Indian rupees with Indian digit grouping: 125000 -> ₹1,25,000."""
    if amount is None or amount == "":
        return ""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    rupees, paise = f"{abs(amount):.2f}".split(".")
    head, tail = rupees[:-3], rupees[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    grouped = ",".join(groups + [tail])
    return f"{sign}₹{grouped}" + ("" if paise == "00" else f".{paise}")


@register.filter
def duration(delta):
    minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h" + (f" {minutes} min" if minutes else "")


@register.inclusion_tag("pages/_chart.html")
def sailing_map(schedule):
    """Route map for one sailing, with the ferry's estimated position."""
    from apps.pages.charts import sailing_chart

    return {"chart": sailing_chart(schedule)}


@register.inclusion_tag("includes/journey_map.html")
def journey_map():
    """Map under the search form that draws the crossing as people pick From and To."""
    from apps.pages.charts import journey_regions

    return {"regions": journey_regions()}
