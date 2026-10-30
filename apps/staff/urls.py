from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sailings/<int:pk>/manifest/", views.manifest, name="manifest"),
    path("reports/", views.reports, name="reports"),
    path("support/", views.support_list, name="support"),
    path("support/<str:reference>/", views.support_detail, name="support_detail"),
]
