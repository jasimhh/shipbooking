from django.contrib import admin

from .models import Ticket, TicketVerificationEvent


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["number", "booking", "status", "issued_at", "voided_at"]
    list_filter = ["status"]
    search_fields = ["number", "booking__reference"]
    readonly_fields = ["booking", "number", "status", "issued_at", "issued_by", "voided_at"]
    exclude = ["verification_token", "pdf"]  # the token is a bearer secret; reissue from the booking instead

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketVerificationEvent)
class TicketVerificationEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "ticket", "result", "verified_by"]
    list_filter = ["result"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
