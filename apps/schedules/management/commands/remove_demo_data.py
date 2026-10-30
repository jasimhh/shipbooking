from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.bookings.models import Booking, BookingSeat, CancellationRequest
from apps.fleet.models import Route, Vessel
from apps.operators.models import Operator
from apps.payments.models import PaymentTransaction, Refund
from apps.schedules.models import InventoryHold, Schedule
from apps.tickets.models import Ticket


class Command(BaseCommand):
    help = "Delete every fictional (is_demo) operator with its vessels, routes, sailings and test bookings. Ports are kept."

    @transaction.atomic
    def handle(self, *args, **options):
        operators = Operator.objects.filter(is_demo=True)
        bookings = Booking.objects.filter(schedule__route__operator__in=operators)
        # Children that protect their parents go first.
        Refund.objects.filter(payment__booking__in=bookings).delete()
        PaymentTransaction.objects.filter(booking__in=bookings).delete()
        CancellationRequest.objects.filter(booking__in=bookings).delete()
        Ticket.objects.filter(booking__in=bookings).delete()
        BookingSeat.objects.filter(booking__in=bookings).delete()
        InventoryHold.objects.filter(booking__in=bookings).delete()
        counts = {"bookings": bookings.delete()[0]}
        counts["sailings"] = Schedule.objects.filter(route__operator__in=operators).delete()[0]
        counts["routes"] = Route.objects.filter(operator__in=operators).delete()[0]
        counts["vessels"] = Vessel.objects.filter(operator__in=operators).delete()[0]
        members = list(User.objects.filter(operator_memberships__operator__in=operators, role=User.Role.OPERATOR))
        counts["operators"] = operators.delete()[0]
        # Operator accounts that only existed for the demo operator.
        counts["operator accounts"] = sum(u.delete()[0] for u in members if not u.operator_memberships.exists())
        for name, n in counts.items():
            self.stdout.write(f"{name}: {n}")
