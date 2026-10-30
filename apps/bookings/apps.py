from django.apps import AppConfig
from django.db.models.signals import post_save


def schedule_saved(sender, instance, created, **kwargs):
    from .cancellation import on_schedule_status_change

    old = getattr(instance, "_loaded_status", None)
    if not created and old is not None:
        on_schedule_status_change(instance, old)
    instance._loaded_status = instance.status


class BookingsConfig(AppConfig):
    name = 'apps.bookings'

    def ready(self):
        post_save.connect(schedule_saved, sender="schedules.Schedule", dispatch_uid="bookings.schedule_saved")
