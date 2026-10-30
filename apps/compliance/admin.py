from django.contrib import admin, messages
from django.utils import timezone

from apps.bookings.models import CancellationRule

from .models import AuditLog, ConsentRecord, CookiePreference, PolicyVersion, PrivacyRequest
from .privacy import StillTravelling, anonymise_user


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


class ReadOnlyAdmin(admin.ModelAdmin):
    """Consent evidence: viewable, never edited by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConsentRecord)
class ConsentRecordAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "user", "anonymous_id", "purpose", "granted", "policy_version"]
    list_filter = ["purpose", "granted"]
    search_fields = ["user__email", "anonymous_id"]


@admin.register(CookiePreference)
class CookiePreferenceAdmin(ReadOnlyAdmin):
    list_display = ["updated_at", "user", "anonymous_id", "analytics", "marketing"]
    list_filter = ["analytics", "marketing"]
    search_fields = ["user__email", "anonymous_id"]


@admin.register(PrivacyRequest)
class PrivacyRequestAdmin(AuditedAdmin):
    list_display = ["created_at", "email", "request_type", "status", "resolved_at"]
    list_filter = ["request_type", "status"]
    search_fields = ["email", "details"]
    readonly_fields = ["user", "email", "request_type", "details", "created_at", "resolved_at"]
    fields = readonly_fields + ["status", "resolution_note"]
    actions = ["mark_in_progress", "anonymise_accounts"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if obj.status in (PrivacyRequest.Status.COMPLETED, PrivacyRequest.Status.REJECTED) and not obj.resolved_at:
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark as in progress")
    def mark_in_progress(self, request, queryset):
        for req in queryset.filter(status=PrivacyRequest.Status.RECEIVED):
            req.status = PrivacyRequest.Status.IN_PROGRESS
            req.save()
            AuditLog.record(request.user, "privacyrequest.updated", req, {"status": req.status}, request)

    @admin.action(description="Delete (anonymise) the account for selected deletion requests")
    def anonymise_accounts(self, request, queryset):
        for req in queryset.filter(request_type=PrivacyRequest.RequestType.DELETION, user__isnull=False):
            try:
                anonymise_user(req.user, request.user, request)
            except StillTravelling as exc:
                self.message_user(request, f"{req.email}: {exc}", messages.ERROR)
                continue
            req.email = req.user.email
            req.status, req.resolved_at = PrivacyRequest.Status.COMPLETED, timezone.now()
            req.resolution_note = req.resolution_note or "Account deleted. Booking amounts and references kept for financial records."
            req.save()
            AuditLog.record(request.user, "privacyrequest.updated", req, {"status": req.status}, request)
            self.message_user(request, "Account anonymised.", messages.SUCCESS)
