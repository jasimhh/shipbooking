from django.conf import settings
from django.db import models

from apps.common import TimeStampedModel


class Operator(TimeStampedModel):
    class Verification(models.TextChoices):
        PENDING = "pending", "Pending verification"
        VERIFIED = "verified", "Verified"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    verification_status = models.CharField(
        max_length=20, choices=Verification.choices, default=Verification.PENDING, db_index=True
    )
    # Fictional demo data must never reach a live booking/payment flow.
    is_demo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class OperatorMembership(TimeStampedModel):
    """Which users act for which operator, and what they may do there."""

    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operator_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    can_edit_schedules = models.BooleanField(default=False)
    can_view_manifests = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["operator", "user"], name="uniq_operator_member")]

    def __str__(self):
        return f"{self.user} @ {self.operator}"
