from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("sailings/<int:pk>/book/", views.details, name="details"),
    path("sailings/<int:pk>/book/review/", views.review, name="review"),
    path("bookings/<str:reference>/", views.detail, name="detail"),
    path("bookings/<str:reference>/cancel/", views.cancel_reservation, name="cancel"),
]
