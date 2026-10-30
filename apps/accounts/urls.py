from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("verify/sent/", views.verification_sent, name="verification_sent"),
    path("verify/resend/", views.resend_verification, name="resend_verification"),
    path("verify/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("sign-in/", views.LoginView.as_view(), name="login"),
    path("sign-out/", views.logout, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("password/change/", views.password_change, name="password_change"),
    path("password/change/done/", views.password_change_done, name="password_change_done"),
    path("password/reset/", views.password_reset, name="password_reset"),
    path("password/reset/sent/", views.password_reset_done, name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("password/reset/done/", views.password_reset_complete, name="password_reset_complete"),
]
