from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.compliance.models import AuditLog

from .models import PassengerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "role", "email_verified", "is_active", "date_joined"]
    list_filter = ["role", "email_verified", "is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Personal", {"fields": ["first_name", "last_name", "phone"]}),
        ("Access", {"fields": ["role", "email_verified", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"], "fields": ["email", "role", "password1", "password2"]})]

    AUDITED = ["role", "is_active", "is_staff", "is_superuser", "email_verified"]

    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            old = User.objects.get(pk=obj.pk)
            before = {f: getattr(old, f) for f in self.AUDITED}
        super().save_model(request, obj, form, change)
        after = {f: getattr(obj, f) for f in self.AUDITED}
        changes = {f: [before.get(f), after[f]] for f in self.AUDITED if before.get(f) != after[f]}
        if changes or not change:
            AuditLog.record(request.user, "user.access_changed" if change else "user.created", obj, changes, request)


admin.site.register(PassengerProfile)
