"""Approximate public coordinates for the demo ports, used to place them on the harbour map.
Admins can correct them in Ports."""

from decimal import Decimal

from django.db import migrations

COORDS = {
    "MUMFW": ("18.958000", "72.846000"),  # Mumbai Ferry Wharf (Bhaucha Dhakka)
    "MDWJ": ("18.806000", "72.882000"),   # Mandwa Jetty
    "PBPBJ": ("11.672000", "92.737000"),  # Phoenix Bay Jetty, Sri Vijaya Puram
    "HVLJ": ("12.035000", "92.982000"),   # Swaraj Dweep (Havelock) jetty
}


def fill(apps, schema_editor):
    Port = apps.get_model("fleet", "Port")
    for code, (lat, lon) in COORDS.items():
        Port.objects.filter(code=code, latitude__isnull=True).update(latitude=Decimal(lat), longitude=Decimal(lon))


class Migration(migrations.Migration):
    dependencies = [("fleet", "0002_port_coordinates")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
