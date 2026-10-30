# Routes

| URL | View | Template | Renders |
|---|---|---|---|
| `/` | pages.views.home | templates/pages/home.html | Navy hero with search card (from/to/date/passengers), announcements, 'How booking works' 4 steps, 'Before you travel' tiles, help buttons |
| `/search/` | pages.views.search | templates/pages/search.html | Search form bar, results header with time filter + sort, list of sailing result rows (times, vessel/operator, duration, from-price ₹, availability badge, View sailing) |
| `/sailings/<id>/` | pages.views.sailing_detail | templates/pages/sailing_detail.html | Journey facts, fares table, facilities, boarding info, guidance sidebar |
| `/help/`, `/help/<slug>/`, `/about/` | help_centre / content_page | help.html / content_page.html | Guide tiles; article with sidebar |
| `/faq/` | faq | faq.html | details/summary accordion |
| `/contact/` | contact | contact.html | Support form + contact details sidebar |
| `/service-updates/` | service_updates | service_updates.html | Announcements + changed sailings table |
| `/policies/<type>/` | policy | policy.html | Policy text or 'not yet published' notice |

### `apps/pages/urls.py`

```python
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

```

