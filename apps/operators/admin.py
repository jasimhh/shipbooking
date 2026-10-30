from django.contrib import admin, messages

from apps.compliance.admin import AuditedAdmin
from apps.compliance.models import AuditLog

from .models import Operator, OperatorMembership


class MembershipInline(admin.TabularInline):
    model = OperatorMembership
    extra = 0
    autocomplete_fields = ["user"]
    fields = ["user", "role", "can_edit_schedules", "can_view_manifests", "is_active"]


@admin.register(Operator)
class OperatorAdmin(AuditedAdmin):
    list_display = ["name", "verification_status", "is_demo", "is_active", "contact_email"]
    list_filter = ["verification_status", "is_demo", "is_active"]
    search_fields = ["name", "legal_name", "contact_email"]
    inlines = [MembershipInline]
    actions = ["mark_verified", "suspend"]

    def _set_status(self, request, queryset, status):
        for op in queryset:
            old = op.verification_status
            op.verification_status = status
            op.save(update_fields=["verification_status"])
            AuditLog.record(request.user, "operator.verification_changed", op, {"verification_status": [old, status]}, request)
        messages.success(request, f"{queryset.count()} operator(s) set to {Operator.Verification(status).label}.")

    @admin.action(description="Mark selected operators as verified")
    def mark_verified(self, request, queryset):
        self._set_status(request, queryset, Operator.Verification.VERIFIED)

    @admin.action(description="Suspend selected operators (their sailings stop being bookable)")
    def suspend(self, request, queryset):
        self._set_status(request, queryset, Operator.Verification.SUSPENDED)
