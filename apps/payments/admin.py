from django.contrib import admin, messages

from apps.compliance.admin import AuditedAdmin
from apps.compliance.models import AuditLog

from . import gateway, services
from .models import GatewayEvent, PaymentTransaction, Refund


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    fields = ["amount", "reason", "status", "gateway_refund_id", "created_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(ReadOnlyAdmin):
    list_display = ["gateway_order_id", "booking", "amount", "status", "is_live", "signature_verified", "captured_at", "created_at"]
    list_filter = ["status", "is_live", "gateway"]
    search_fields = ["gateway_order_id", "gateway_payment_id", "booking__reference"]
    date_hierarchy = "created_at"
    inlines = [RefundInline]
    actions = ["reconcile_selected"]

    def has_change_permission(self, request, obj=None):
        return obj is None  # lets the changelist run actions; individual records stay read-only

    @admin.action(description="Check selected orders with Razorpay and settle paid ones")
    def reconcile_selected(self, request, queryset):
        if not gateway.is_configured():
            messages.error(request, "Razorpay keys aren't configured.")
            return
        settled = 0
        for txn in queryset.filter(status=PaymentTransaction.Status.CREATED):
            paid = [p for p in gateway.order_payments(txn.gateway_order_id) if p.get("status") in ("captured", "authorized")]
            if paid:
                try:
                    services.record_success(txn, paid[0]["id"])
                    AuditLog.record(request.user, "payment.reconciled", txn, {"payment": paid[0]["id"]}, request)
                    settled += 1
                except services.PaymentError as e:
                    messages.warning(request, f"{txn}: {e}")
        messages.success(request, f"Settled {settled} payment(s).")


@admin.register(GatewayEvent)
class GatewayEventAdmin(ReadOnlyAdmin):
    list_display = ["received_at", "event_type", "event_id", "signature_valid", "processed_at", "processing_error"]
    list_filter = ["event_type", "signature_valid"]
    search_fields = ["event_id"]


@admin.register(Refund)
class RefundAdmin(AuditedAdmin):
    list_display = ["payment", "amount", "reason", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["payment", "cancellation_request", "amount", "reason", "gateway_refund_id", "initiated_by"]

    def has_add_permission(self, request):
        return False
