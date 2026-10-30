import secrets

from django.db import models

MONEY = {"max_digits": 12, "decimal_places": 2}
# No 0/O/1/I so references can be read out over the phone.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def make_reference(prefix, length=8):
    return prefix + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
