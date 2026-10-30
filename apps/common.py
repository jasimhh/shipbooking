import secrets

from django.core.cache import cache
from django.db import models

MONEY = {"max_digits": 12, "decimal_places": 2}
# No 0/O/1/I so references can be read out over the phone.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def make_reference(prefix, length=8):
    return prefix + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))


def client_ip(request):
    """Behind Nginx set TRUSTED_PROXY_HEADER=HTTP_X_REAL_IP. Nginx overwrites that header, so clients can't fake it."""
    from django.conf import settings

    header = settings.TRUSTED_PROXY_HEADER
    return (request.META.get(header, "").strip() if header else "") or request.META.get("REMOTE_ADDR", "")


# Counters live in settings.CACHES (a database table by default, shared by every worker).
# ponytail: database cache; switch CACHES to Redis if rate-limit traffic ever gets heavy.
def is_rate_limited(key, limit):
    return cache.get(key, 0) >= limit


def record_attempt(key, window_seconds):
    cache.add(key, 0, window_seconds)
    return cache.incr(key)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

