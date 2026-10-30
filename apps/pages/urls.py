from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("sailings/<int:pk>/", views.sailing_detail, name="sailing"),
    path("about/", views.content_page, {"slug": "about", "section": "about"}, name="about"),
    path("help/", views.help_centre, name="help"),
    path("help/<slug:slug>/", views.content_page, name="guide"),
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("service-updates/", views.service_updates, name="service_updates"),
    path("policies/<slug:policy_type>/", views.policy, name="policy"),
]
