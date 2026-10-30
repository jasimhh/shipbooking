from django.apps import apps
from django.contrib import admin

admin.site.register(apps.get_app_config("tickets").get_models())
