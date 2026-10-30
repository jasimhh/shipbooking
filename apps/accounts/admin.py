from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

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


admin.site.register(PassengerProfile)
