from django.contrib import admin

from .models import AuditLog, ConsentRecord, CookiePreference, PolicyVersion, PrivacyRequest

admin.site.register([PolicyVersion, CookiePreference, ConsentRecord, PrivacyRequest])


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "action", "object_type", "object_id"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_id", "actor__email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
