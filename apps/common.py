import secrets

from django.core.cache import cache
from django.db import models

MONEY = {"max_digits": 12, "decimal_places": 2}
# No 0/O/1/I so references can be read out over the phone.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def make_reference(prefix, length=8):
    return prefix + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))


def client_ip(request):
    # ponytail: trusts REMOTE_ADDR; behind Nginx set it from the proxy header (Phase 10).
    return request.META.get("REMOTE_ADDR", "")


# ponytail: counters live in the per-process cache; use a shared cache (Redis) with several app servers.
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
