import json
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.common import is_rate_limited, record_attempt

from .models import AuditLog, ConsentRecord, CookiePreference, PolicyVersion, PrivacyRequest
from .privacy import export_user_data

CONSENT_COOKIE = "cookie_consent"
PURPOSES = ["analytics", "marketing"]


def read_consent(request):
    """Cookie value looks like 'a0m1.<anonymous id>'. Missing or malformed means no choice made yet."""
    value = request.COOKIES.get(CONSENT_COOKIE, "")
    flags, _, anon = value.partition(".")
    if len(flags) != 4 or flags[0] != "a" or flags[2] != "m" or flags[1] not in "01" or flags[3] not in "01":
        return {"decided": False, "analytics": False, "marketing": False, "anonymous_id": ""}
    return {"decided": True, "analytics": flags[1] == "1", "marketing": flags[3] == "1", "anonymous_id": anon[:64]}


def consent(request):
    """Context processor: optional scripts must sit inside {% if consent.analytics %} / {% if consent.marketing %}."""
    return {"consent": read_consent(request)}


def _safe_next(request):
    target = request.POST.get("next") or request.GET.get("next") or "/"
    return target if url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()) else "/"


def _current_cookie_policy():
    return (PolicyVersion.objects.filter(policy_type=PolicyVersion.PolicyType.COOKIES, is_published=True,
                                         effective_from__lte=timezone.now()).order_by("-effective_from").first())


@require_POST
def save_cookies(request):
    choice = request.POST.get("choice")
    if choice == "accept":
        chosen = {p: True for p in PURPOSES}
    elif choice == "reject":
        chosen = {p: False for p in PURPOSES}
    else:
        chosen = {p: request.POST.get(p) == "on" for p in PURPOSES}
    anon = read_consent(request)["anonymous_id"] or secrets.token_urlsafe(16)
    user = request.user if request.user.is_authenticated else None
    if user:
        CookiePreference.objects.update_or_create(user=user, defaults=chosen)
    else:
        CookiePreference.objects.update_or_create(anonymous_id=anon, defaults=chosen)
    policy = _current_cookie_policy()
    ConsentRecord.objects.bulk_create([
        ConsentRecord(user=user, anonymous_id="" if user else anon, purpose=p, granted=granted, policy_version=policy)
        for p, granted in chosen.items()
    ])
    messages.success(request, "Cookie choices saved.")
    response = redirect(_safe_next(request))
    response.set_cookie(CONSENT_COOKIE, f"a{int(chosen['analytics'])}m{int(chosen['marketing'])}.{anon}",
                        max_age=settings.COOKIE_CONSENT_DAYS * 86400, samesite="Lax",
                        secure=settings.SESSION_COOKIE_SECURE, httponly=True)
    return response


def cookie_settings(request):
    return render(request, "compliance/cookies.html", {"next": _safe_next(request)})


class PrivacyRequestForm(forms.ModelForm):
    class Meta:
        model = PrivacyRequest
        fields = ["request_type", "details"]
        labels = {"request_type": "What would you like us to do?", "details": "Details"}
        help_texts = {"details": "For corrections, say what is wrong and what it should be."}
        widgets = {"details": forms.Textarea(attrs={"rows": 4})}


def privacy_centre(request):
    form = None
    if request.user.is_authenticated:
        form = PrivacyRequestForm(request.POST or None)
        if request.method == "POST":
            key = f"privacy-request:{request.user.pk}"
            if is_rate_limited(key, 5):
                form.add_error(None, "You have sent several requests today. We will reply to those first.")
            elif form.is_valid():
                record_attempt(key, 86400)
                req = form.save(commit=False)
                req.user, req.email = request.user, request.user.email
                req.save()
                AuditLog.record(request.user, "privacy_request.created", req, {"type": req.request_type}, request)
                messages.success(request, "Request received. We will reply by email.")
                return redirect("compliance:privacy")
    return render(request, "compliance/privacy.html", {
        "form": form,
        "requests": PrivacyRequest.objects.filter(user=request.user).order_by("-created_at") if request.user.is_authenticated else [],
    })


@login_required
def my_data(request):
    AuditLog.record(request.user, "privacy.data_exported", request.user, {}, request)
    response = HttpResponse(json.dumps(export_user_data(request.user), cls=DjangoJSONEncoder, indent=2),
                            content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="ship-booking-my-data.json"'
    response["Cache-Control"] = "private, no-store"
    return response
