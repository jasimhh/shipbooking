from django.urls import path

from . import views

app_name = "tickets"

urlpatterns = [
    path("bookings/<str:reference>/ticket.pdf", views.ticket_pdf, name="pdf"),
    path("tickets/verify/<str:token>/", views.verify, name="verify"),
    path("tickets/verify/<str:token>/board/", views.board, name="board"),
]
