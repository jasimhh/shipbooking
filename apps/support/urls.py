from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.my_tickets, name="mine"),
    path("<str:reference>/", views.ticket, name="ticket"),
    path("<str:reference>/reply/", views.reply, name="reply"),
]
