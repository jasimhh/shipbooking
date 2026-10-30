from django.contrib import admin, messages

from apps.compliance.admin import AuditedAdmin
from apps.compliance.models import AuditLog

from .models import Fare, InventoryHold, Schedule


class FareInline(admin.TabularInline):
    model = Fare
    extra = 0
    fields = ["cabin_class", "base_fare", "tax_amount", "fee_amount", "capacity", "units_allocated", "fare_rules"]
    readonly_fields = ["units_allocated"]


@admin.register(Schedule)
class ScheduleAdmin(AuditedAdmin):
    list_display = ["__str__", "vessel", "departure_at", "arrival_at", "status", "places_sold"]
    list_filter = ["status", "route__operator", "route"]
    search_fields = ["route__origin__name", "route__destination__name", "vessel__name"]
    date_hierarchy = "departure_at"
    autocomplete_fields = ["route", "vessel"]
    inlines = [FareInline]
    actions = ["publish", "cancel"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("route__origin", "route__destination", "vessel").prefetch_related("fares")

    @admin.display(description="Sold or held / capacity")
    def places_sold(self, schedule):
        fares = schedule.fares.all()
        return f"{sum(f.units_allocated for f in fares)} / {sum(f.capacity for f in fares)}"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        schedule = form.instance
        if schedule.status in Schedule.LIVE and (problems := schedule.publish_problems()):
            schedule.status = Schedule.Status.DRAFT
            schedule.save(update_fields=["status"])
            messages.warning(request, f"Saved as a draft because {' and '.join(problems)}.")

    @admin.action(description="Approve and publish selected sailings")
    def publish(self, request, queryset):
        published, blocked = 0, []
        for schedule in queryset.filter(status__in=Schedule.EDITABLE):
            if problems := schedule.publish_problems():
                blocked.append(f"{schedule} ({', '.join(problems)})")
                continue
            schedule.status = Schedule.Status.PUBLISHED
            schedule.save(update_fields=["status"])
            AuditLog.record(request.user, "schedule.published", schedule, {}, request)
            published += 1
        messages.success(request, f"Published {published} sailing(s).")
        if blocked:
            messages.warning(request, "Not published: " + "; ".join(blocked))

    @admin.action(description="Cancel selected sailings")
    def cancel(self, request, queryset):
        # ponytail: passengers aren't notified yet; booking notifications arrive in Phase 7.
        n = 0
        for schedule in queryset.exclude(status__in=[Schedule.Status.CANCELLED, Schedule.Status.COMPLETED]):
            old = schedule.status
            schedule.status = Schedule.Status.CANCELLED
            schedule.save(update_fields=["status"])
            AuditLog.record(request.user, "schedule.cancelled", schedule, {"status": [old, schedule.status]}, request)
            n += 1
        messages.success(request, f"Cancelled {n} sailing(s).")


@admin.register(InventoryHold)
class InventoryHoldAdmin(admin.ModelAdmin):
    list_display = ["booking", "fare", "quantity", "status", "expires_at"]
    list_filter = ["status"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
