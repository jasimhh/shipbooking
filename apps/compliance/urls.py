from django.urls import path

from . import views

app_name = "compliance"

urlpatterns = [
    path("", views.privacy_centre, name="privacy"),
    path("cookies/", views.cookie_settings, name="cookies"),
    path("cookies/save/", views.save_cookies, name="save_cookies"),
    path("my-data.json", views.my_data, name="my_data"),
]
