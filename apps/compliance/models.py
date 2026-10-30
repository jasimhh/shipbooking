from django.conf import settings
from django.db import models

from apps.common import TimeStampedModel


class AuditLog(models.Model):
    """Append-only record of administrative and financial actions."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit log entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries cannot be deleted.")


class PolicyVersion(TimeStampedModel):
    class PolicyType(models.TextChoices):
        PRIVACY = "privacy", "Privacy Policy"
        TERMS = "terms", "Terms and Conditions"
        COOKIES = "cookies", "Cookie Policy"
        CANCELLATION = "cancellation", "Cancellation Policy"
        REFUND = "refund", "Refund Policy"
        PAYMENT = "payment", "Payment Policy"
        ACCESSIBILITY = "accessibility", "Accessibility Statement"
        DISCLAIMER = "disclaimer", "Disclaimer"
        RETENTION = "retention", "Data Retention Policy"
        ACCEPTABLE_USE = "acceptable_use", "Acceptable Use Policy"
        COPYRIGHT = "copyright", "Copyright and IP Policy"
        GRIEVANCE = "grievance", "Grievance Redressal Policy"

    policy_type = models.CharField(max_length=30, choices=PolicyType.choices)
    version = models.CharField(max_length=20)
    body = models.TextField()
    effective_from = models.DateTimeField()
    is_published = models.BooleanField(default=False)
    # Must be approved (legal review / operator terms) before publishing.
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["policy_type", "-effective_from"]
        constraints = [models.UniqueConstraint(fields=["policy_type", "version"], name="uniq_policy_version")]

    def __str__(self):
        return f"{self.get_policy_type_display()} v{self.version}"


class CookiePreference(TimeStampedModel):
    """Current optional-cookie choices. Essential cookies are always on and not stored here."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="cookie_preference"
    )
    anonymous_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    analytics = models.BooleanField(default=False)
    marketing = models.BooleanField(default=False)


class ConsentRecord(models.Model):
    """Every consent given or withdrawn, kept as evidence."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    anonymous_id = models.CharField(max_length=64, blank=True, db_index=True)
    purpose = models.CharField(max_length=50)
    granted = models.BooleanField()
    policy_version = models.ForeignKey(PolicyVersion, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PrivacyRequest(TimeStampedModel):
    class RequestType(models.TextChoices):
        ACCESS = "access", "Access my data"
        CORRECTION = "correction", "Correct my data"
        DELETION = "deletion", "Delete my data"
        WITHDRAW_CONSENT = "withdraw_consent", "Withdraw consent"
        GRIEVANCE = "grievance", "Privacy grievance"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField()
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
