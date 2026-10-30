from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common import TimeStampedModel


class ContentPage(TimeStampedModel):
    class Section(models.TextChoices):
        ABOUT = "about", "About"
        GUIDE = "guide", "Help centre guide"

    slug = models.SlugField(unique=True)
    section = models.CharField(max_length=10, choices=Section.choices, default=Section.GUIDE)
    title = models.CharField(max_length=150)
    summary = models.CharField(max_length=255, help_text="Shown in listings and as the meta description.")
    # ponytail: trusted HTML from staff via admin; switch to a sanitiser if non-staff ever edit content.
    body = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class FAQ(TimeStampedModel):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class AnnouncementQuerySet(models.QuerySet):
    def current(self):
        now = timezone.now()
        return self.filter(is_published=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))


class Announcement(TimeStampedModel):
    class Level(models.TextChoices):
        INFO = "info", "Information"
        DISRUPTION = "disruption", "Service disruption"

    title = models.CharField(max_length=200)
    body = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.title
