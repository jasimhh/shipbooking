"""Operator portal at /operator/: a separate admin site scoped to the signed-in user's operators.

Every queryset, form choice and permission check here goes through apps.accounts.permissions,
so operator staff can never read or change another operator's records.
Operators draft sailings and submit them for approval; only platform admins publish.
"""

from functools import wraps

from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.forms import ModelForm

from apps.accounts.permissions import can_edit_schedules, memberships, operators_for
from apps.compliance.admin import AuditedAdmin
from apps.fleet.models import CabinClass, Route, Vessel
from apps.schedules.models import Fare, Schedule

S = Schedule.Status
# Which statuses an operator may move a sailing to, by its current status.
OPERATOR_TRANSITIONS = {
    None: [S.DRAFT, S.PENDING_APPROVAL],
    S.DRAFT: [S.DRAFT, S.PENDING_APPROVAL],
    S.PENDING_APPROVAL: [S.DRAFT, S.PENDING_APPROVAL],
    S.PUBLISHED: [S.PUBLISHED, S.DELAYED, S.CANCELLED],
    S.DELAYED: [S.DELAYED, S.PUBLISHED, S.CANCELLED],
}


class OperatorSite(admin.AdminSite):
    site_header = "Ship Booking · Operator portal"
    site_title = "Operator portal"
    index_title = "Your vessels, routes and sailings"
    site_url = "/"

    def has_permission(self, request):
        user = request.user
        return user.is_active and (user.is_platform_admin or memberships(user).exists())

    def login(self, request, extra_context=None):
        return redirect_to_login(request.GET.get("next", request.get_full_path()))

    def admin_view(self, view, cacheable=False):
        inner = super().admin_view(view, cacheable)

        @wraps(inner)
        def wrapper(request, *args, **kwargs):
            # Signed in but not operator staff: refuse, rather than bouncing to the sign-in page.
            if request.user.is_authenticated and not self.has_permission(request):
                raise PermissionDenied
            return inner(request, *args, **kwargs)
        return wrapper


operator_site = OperatorSite(name="operator")


class ScopedAdmin(admin.ModelAdmin):
    """Read-only by default; querysets limited to the user's operators."""

    operator_path = "operator"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(**{f"{self.operator_path}__in": operators_for(request.user)})

    def has_module_permission(self, request):
        return operator_site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return operator_site.has_permission(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CabinClassInline(admin.TabularInline):
    model = CabinClass
    fields = ["code", "name", "capacity"]
    extra = 0

    def has_view_permission(self, request, obj=None):
        return True


@admin.register(Vessel, site=operator_site)
class VesselPortalAdmin(ScopedAdmin):
    list_display = ["name", "vessel_type", "seating_mode", "is_active"]
    inlines = [CabinClassInline]


@admin.register(Route, site=operator_site)
class RoutePortalAdmin(ScopedAdmin):
    list_display = ["__str__", "origin", "destination", "is_active"]


class FareInline(admin.TabularInline):
    model = Fare
    extra = 0
    fields = ["cabin_class", "base_fare", "tax_amount", "fee_amount", "capacity", "units_allocated", "fare_rules"]
    readonly_fields = ["units_allocated"]

    def editable(self, request, obj):
        return obj is None or (obj.status in Schedule.EDITABLE and can_edit_schedules(request.user, obj.route.operator))

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return self.editable(request, obj)

    def has_change_permission(self, request, obj=None):
        return self.editable(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.editable(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "cabin_class":
            kwargs["queryset"] = CabinClass.objects.filter(vessel__operator__in=operators_for(request.user))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ScheduleForm(ModelForm):
    class Meta:
        model = Schedule
        fields = "__all__"

    def clean_status(self):
        status = self.cleaned_data["status"]
        current = self.instance.status if self.instance.pk else None
        if status not in OPERATOR_TRANSITIONS.get(current, [current]):
            raise ValidationError("You can't move a sailing to this status. Publishing needs platform approval.")
        return status


@admin.register(Schedule, site=operator_site)
class SchedulePortalAdmin(ScopedAdmin, AuditedAdmin):
    operator_path = "route__operator"
    form = ScheduleForm
    list_display = ["__str__", "vessel", "departure_at", "status", "places_sold"]
    list_filter = ["status", "route"]
    date_hierarchy = "departure_at"
    fields = ["route", "vessel", "departure_at", "arrival_at", "booking_closes_at", "status", "status_note"]
    inlines = [FareInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("route__origin", "route__destination", "vessel").prefetch_related("fares")

    @admin.display(description="Sold or held / capacity")
    def places_sold(self, schedule):
        fares = schedule.fares.all()
        return f"{sum(f.units_allocated for f in fares)} / {sum(f.capacity for f in fares)}"

    def has_add_permission(self, request, obj=None):
        return request.user.is_platform_admin or memberships(request.user, can_edit_schedules=True).exists()

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return self.has_add_permission(request)
        return obj.status in OPERATOR_TRANSITIONS and can_edit_schedules(request.user, obj.route.operator)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status not in Schedule.EDITABLE:
            # Live sailings: operators may only report delays, cancellations and notes.
            return ["route", "vessel", "departure_at", "arrival_at", "booking_closes_at"]
        return []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        editable_ops = [op for op in operators_for(request.user) if can_edit_schedules(request.user, op)]
        if db_field.name == "route":
            kwargs["queryset"] = Route.objects.filter(operator__in=editable_ops, is_active=True)
        elif db_field.name == "vessel":
            kwargs["queryset"] = Vessel.objects.filter(operator__in=editable_ops, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
