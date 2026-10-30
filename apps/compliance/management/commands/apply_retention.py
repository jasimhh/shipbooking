from django.core.management.base import BaseCommand

from apps.compliance.privacy import apply_retention


class Command(BaseCommand):
    help = "Remove personal data past the retention periods in settings.RETENTION. Run daily from cron."

    def handle(self, *args, **options):
        for name, count in apply_retention().items():
            self.stdout.write(f"{name.replace('_', ' ')}: {count}")
