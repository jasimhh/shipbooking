from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("bookings/<str:reference>/pay/", views.pay, name="pay"),
    path("bookings/<str:reference>/pay/return/", views.checkout_return, name="return"),
    path("bookings/<str:reference>/pay/failed/", views.checkout_failed, name="failed"),
    path("payments/webhooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
