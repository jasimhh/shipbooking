from django.contrib import admin, messages

from apps.compliance.admin import AuditedAdmin
from apps.compliance.models import AuditLog

from .models import CabinClass, Port, Route, Seat, Vessel


@admin.register(Port)
class PortAdmin(AuditedAdmin):
    list_display = ["name", "code", "city", "state", "is_active"]
    list_filter = ["state", "is_active"]
    search_fields = ["name", "code", "city"]


@admin.register(Route)
class RouteAdmin(AuditedAdmin):
    list_display = ["__str__", "origin", "destination", "operator", "distance_km", "is_active"]
    list_filter = ["is_active", "operator", "origin__state"]
    search_fields = ["origin__name", "destination__name", "operator__name"]
    autocomplete_fields = ["origin", "destination", "operator"]


class CabinClassInline(admin.TabularInline):
    model = CabinClass
    extra = 0
    fields = ["code", "name", "capacity"]


@admin.register(Vessel)
class VesselAdmin(AuditedAdmin):
    list_display = ["name", "operator", "vessel_type", "seating_mode", "total_capacity", "is_active"]
    list_filter = ["operator", "seating_mode", "is_active"]
    search_fields = ["name", "imo_number", "operator__name"]
    autocomplete_fields = ["operator"]
    inlines = [CabinClassInline]
    actions = ["create_seats"]

    @admin.display(description="Capacity")
    def total_capacity(self, vessel):
        return sum(c.capacity for c in vessel.cabin_classes.all())

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("operator").prefetch_related("cabin_classes")

    @admin.action(description="Create numbered seats for each cabin class (assigned seating only)")
    def create_seats(self, request, queryset):
        created = 0
        for vessel in queryset.filter(seating_mode=Vessel.SeatingMode.ASSIGNED):
            for cabin in vessel.cabin_classes.all():
                existing = set(cabin.seats.values_list("number", flat=True))
                new = [Seat(cabin_class=cabin, number=f"{cabin.code}-{n:03d}")
                       for n in range(1, cabin.capacity + 1) if f"{cabin.code}-{n:03d}" not in existing]
                Seat.objects.bulk_create(new)
                created += len(new)
            AuditLog.record(request.user, "vessel.seats_created", vessel, {"created": created}, request)
        skipped = queryset.exclude(seating_mode=Vessel.SeatingMode.ASSIGNED).count()
        messages.success(request, f"Created {created} seat(s)." + (f" Skipped {skipped} capacity-based vessel(s)." if skipped else ""))


@admin.register(Seat)
class SeatAdmin(AuditedAdmin):
    list_display = ["number", "cabin_class", "is_active"]
    list_filter = ["cabin_class__vessel", "is_active"]
    search_fields = ["number", "cabin_class__vessel__name"]
