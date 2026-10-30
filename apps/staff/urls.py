from django.urls import path

from . import harbour, views

app_name = "staff"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("harbour/", harbour.harbour, name="harbour"),
    path("harbour/sailings/<int:pk>/passengers.json", harbour.harbour_passengers, name="harbour_passengers"),
    path("harbour/ferries/add/", harbour.add_ferry, name="harbour_add_ferry"),
    path("sailings/<int:pk>/manifest/", views.manifest, name="manifest"),
    path("reports/", views.reports, name="reports"),
    path("support/", views.support_list, name="support"),
    path("support/<str:reference>/", views.support_detail, name="support_detail"),
]
