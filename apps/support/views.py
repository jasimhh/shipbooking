from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import SupportMessage, SupportTicket

CLOSED = [SupportTicket.Status.CLOSED]


def own_tickets(user):
    mine = Q(user=user)
    if user.email_verified:
        mine |= Q(user__isnull=True, contact_email__iexact=user.email)
    return SupportTicket.objects.filter(mine)


@login_required
def my_tickets(request):
    return render(request, "support/my_tickets.html", {"tickets": own_tickets(request.user).order_by("-updated_at")})


@login_required
def ticket(request, reference):
    t = get_object_or_404(own_tickets(request.user), reference=reference)
    return render(request, "support/ticket.html", {"ticket": t, "thread": t.messages.all()})


@login_required
@require_POST
def reply(request, reference):
    t = get_object_or_404(own_tickets(request.user), reference=reference)
    body = request.POST.get("body", "").strip()[:5000]
    if t.status in CLOSED:
        messages.error(request, "This request is closed. Please start a new one from the contact page.")
    elif not body:
        messages.error(request, "Please write a message.")
    else:
        SupportMessage.objects.create(ticket=t, author=request.user, body=body)
        t.status = SupportTicket.Status.OPEN
        t.resolved_at = None
        t.save(update_fields=["status", "resolved_at", "updated_at"])
        messages.success(request, "Message sent.")
    return redirect("support:ticket", reference=reference)
