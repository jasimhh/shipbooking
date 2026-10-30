from django.contrib import admin

from apps.bookings.models import CancellationRule

from .models import AuditLog, ConsentRecord, CookiePreference, PolicyVersion, PrivacyRequest

admin.site.register([CookiePreference, ConsentRecord, PrivacyRequest])


def _label(obj):
    return obj._meta.model_name


class AuditedAdmin(admin.ModelAdmin):
    """Writes every create, edit and delete (including inline rows) to the audit log."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        changes = {f: str(form.cleaned_data.get(f)) for f in form.changed_data}
        AuditLog.record(request.user, f"{_label(obj)}.{'updated' if change else 'created'}", obj, changes, request)

    def delete_model(self, request, obj):
        AuditLog.record(request.user, f"{_label(obj)}.deleted", obj, {"was": str(obj)}, request)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            AuditLog.record(request.user, f"{_label(obj)}.deleted", obj, {"was": str(obj)}, request)
        super().delete_queryset(request, queryset)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        for obj in formset.new_objects:
            AuditLog.record(request.user, f"{_label(obj)}.created", obj, {}, request)
        for obj, fields in formset.changed_objects:
            AuditLog.record(request.user, f"{_label(obj)}.updated", obj, {"fields": fields}, request)
        for obj in formset.deleted_objects:
            AuditLog.record(request.user, f"{_label(obj)}.deleted", obj, {"was": str(obj)}, request)


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


class CancellationRuleInline(admin.TabularInline):
    model = CancellationRule
    extra = 0
    verbose_name = "refund band (cancellation policies only)"


@admin.register(PolicyVersion)
class PolicyVersionAdmin(AuditedAdmin):
    list_display = ["policy_type", "version", "effective_from", "is_published", "approved_by"]
    list_filter = ["policy_type", "is_published"]
    inlines = [CancellationRuleInline]
