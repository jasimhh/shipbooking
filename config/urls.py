from django.contrib import admin
from django.urls import include, path

from apps.operators.portal import operator_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("operator/", operator_site.urls),
    path("account/", include("apps.accounts.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.pages.urls")),
]
