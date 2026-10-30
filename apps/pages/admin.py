from django.contrib import admin

from .models import FAQ, Announcement, ContentPage


@admin.register(ContentPage)
class ContentPageAdmin(admin.ModelAdmin):
    list_display = ["title", "section", "slug", "sort_order", "is_published", "updated_at"]
    list_filter = ["section", "is_published"]
    prepopulated_fields = {"slug": ["title"]}


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["question", "sort_order", "is_published"]
    list_editable = ["sort_order", "is_published"]


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "level", "starts_at", "ends_at", "is_published"]
    list_filter = ["level", "is_published"]
