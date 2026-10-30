from django.contrib import admin, messages

from apps.compliance.admin import AuditedAdmin
from apps.compliance.models import AuditLog
from apps.payments.services import PaymentError
from apps.tickets import services as tickets

from . import cancellation
from .models import Booking, BookingPassenger, BookingStatusHistory, CancellationRequest


class PassengerInline(admin.TabularInline):
    model = BookingPassenger
    extra = 0
    can_delete = False
    readonly_fields = ["full_name", "age", "gender"]

    def has_add_permission(self, request, obj=None):
        return False


class HistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ["created_at", "from_status", "to_status", "changed_by", "note"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["reference", "schedule", "status", "passenger_count", "total_amount", "contact_email", "created_at"]
    list_filter = ["status", "schedule__route__operator"]
    search_fields = ["reference", "contact_email", "passengers__full_name"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in Booking._meta.fields]
    inlines = [PassengerInline, HistoryInline]
    actions = ["reissue_tickets"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Reissue e-tickets (voids the old QR codes)")
    def reissue_tickets(self, request, queryset):
        n = 0
        for booking in queryset.filter(status=Booking.Status.CONFIRMED):
            ticket = tickets.issue(booking, by=request.user)
            AuditLog.record(request.user, "ticket.reissued", ticket, {"booking": booking.reference}, request)
            n += 1
        messages.success(request, f"Reissued {n} ticket(s). Only confirmed bookings get tickets.")


@admin.register(CancellationRequest)
class CancellationRequestAdmin(AuditedAdmin):
    list_display = ["booking", "status", "eligible_refund_amount", "policy_version", "created_at", "decided_by"]
    list_filter = ["status"]
    search_fields = ["booking__reference", "booking__contact_email"]
    readonly_fields = ["booking", "requested_by", "reason", "status", "policy_version", "decided_by", "decided_at"]
    fields = ["booking", "requested_by", "reason", "policy_version", "eligible_refund_amount", "status", "decision_note", "decided_by", "decided_at"]
    actions = ["approve", "reject"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        # Admins may adjust the refund amount only while the request is undecided.
        if obj and obj.status != CancellationRequest.Status.REQUESTED:
            return self.readonly_fields + ["eligible_refund_amount", "decision_note"]
        return self.readonly_fields

    @admin.action(description="Approve: cancel the booking and queue the refund shown")
    def approve(self, request, queryset):
        for req in queryset.filter(status=CancellationRequest.Status.REQUESTED):
            try:
                cancellation.approve(req, request.user)
                AuditLog.record(request.user, "cancellation.approved", req, {"refund": str(req.eligible_refund_amount)}, request)
            except (cancellation.CancellationError, PaymentError) as e:
                messages.error(request, f"{req.booking}: {e}")
        messages.success(request, "Done. Send queued refunds from Payments → Refunds.")

    @admin.action(description="Reject (uses each request's decision note)")
    def reject(self, request, queryset):
        for req in queryset.filter(status=CancellationRequest.Status.REQUESTED):
            if cancellation.reject(req, request.user, req.decision_note):
                AuditLog.record(request.user, "cancellation.rejected", req, {"note": req.decision_note}, request)
        messages.success(request, "Rejected. Passengers have been emailed.")
