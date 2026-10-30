from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape

from apps.compliance.models import PolicyVersion

from .models import ContentPage

# Personal or transactional areas: never indexed, whatever the template says.
PRIVATE_PREFIXES = ("/account/", "/bookings/", "/staff/", "/admin/", "/operator/", "/tickets/", "/payments/",
                    "/privacy/my-", "/search/", "/find-booking/")


class NoIndexPrivateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(PRIVATE_PREFIXES) or "/book/" in request.path:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response


def robots_txt(request):
    lines = ["User-agent: *"] + [f"Disallow: {p}" for p in PRIVATE_PREFIXES] + [
        "Disallow: /sailings/*/book/", f"Sitemap: {settings.SITE_URL}{reverse('sitemap')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def sitemap_xml(request):
    # Demo sailings are left out on purpose: they are fictional and change daily.
    paths = [reverse(name) for name in ["pages:home", "pages:about", "pages:help", "pages:faq", "pages:contact",
                                        "pages:service_updates", "compliance:cookies"]]
    paths += [reverse("pages:guide", args=[slug]) for slug in
              ContentPage.objects.filter(is_published=True, section=ContentPage.Section.GUIDE).values_list("slug", flat=True)]
    paths += [reverse("pages:policy", args=[value]) for value in PolicyVersion.PolicyType.values]
    urls = "".join(f"<url><loc>{escape(settings.SITE_URL + p)}</loc></url>" for p in paths)
    return HttpResponse('<?xml version="1.0" encoding="UTF-8"?>\n'
                        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                        content_type="application/xml")
