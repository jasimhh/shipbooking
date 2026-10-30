from django.contrib import admin
from django.urls import include, path

from apps.operators.portal import operator_site
from apps.pages.seo import health, robots_txt, sitemap_xml

urlpatterns = [
    path("admin/", admin.site.urls),
    path("operator/", operator_site.urls),
    path("staff/", include("apps.staff.urls")),
    path("privacy/", include("apps.compliance.urls")),
    path("robots.txt", robots_txt),
    path("healthz", health, name="health"),
    path("sitemap.xml", sitemap_xml, name="sitemap"),
    path("account/support/", include("apps.support.urls")),
    path("account/", include("apps.accounts.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.tickets.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.pages.urls")),
]
