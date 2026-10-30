from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.common import TimeStampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.ADMIN, email_verified=True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        PASSENGER = "passenger", "Passenger"
        OPERATOR = "operator", "Operator"
        SUPPORT = "support", "Support staff"
        ADMIN = "admin", "Administrator"

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PASSENGER, db_index=True)
    email_verified = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email


class PassengerProfile(TimeStampedModel):
    """Saved details to prefill bookings. Only what a journey needs."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="passenger_profile")
    full_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.full_name or self.user.email
