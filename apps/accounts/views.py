from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST

from apps.common import client_ip, is_rate_limited, record_attempt

from .forms import (
    ChangePasswordForm, EmailLoginForm, NewPasswordForm, ProfileForm, RegistrationForm, ResetForm,
)
from .models import User

LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60
RESEND_LIMIT_PER_HOUR = 3


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "apps.accounts.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        # Changes once the email is verified or changed, so each link works once.
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


verification_tokens = EmailVerificationTokenGenerator()


def send_verification_email(request, user):
    link = request.build_absolute_uri(reverse("accounts:verify_email", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": verification_tokens.make_token(user),
    }))
    body = render_to_string("accounts/email/verify_email.txt", {"user": user, "link": link})
    send_mail("Confirm your email for Ship Booking", body, None, [user.email])


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        send_verification_email(request, user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("accounts:verification_sent")
    return render(request, "accounts/form_page.html", {
        "form": form,
        "title": "Create an account",
        "heading": "Become a passenger",
        "intro": "You'll need an account to book. We'll send a link to confirm your email address.",
        "submit_label": "Create account",
        "after_form": "register",
    })


def verify_email(request, uidb64, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not verification_tokens.check_token(user, token):
        return render(request, "accounts/message_page.html", {
            "title": "This link has expired or was already used",
            "body": "Sign in and request a new confirmation email from your account page.",
            "link_url": reverse("accounts:dashboard"), "link_label": "Go to your account",
        }, status=400)
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    return render(request, "accounts/message_page.html", {
        "title": "Email confirmed",
        "body": "Thanks. Your email address is confirmed.",
        "link_url": reverse("accounts:dashboard"), "link_label": "Go to your account",
    })


@login_required
def verification_sent(request):
    return render(request, "accounts/message_page.html", {
        "title": "Check your email",
        "body": f"We've sent a confirmation link to {request.user.email}. The link expires in 3 days.",
        "link_url": reverse("accounts:dashboard"), "link_label": "Go to your account",
    })


@login_required
@require_POST
def resend_verification(request):
    key = f"verify-resend:{request.user.pk}"
    if request.user.email_verified:
        messages.info(request, "Your email is already confirmed.")
    elif is_rate_limited(key, RESEND_LIMIT_PER_HOUR):
        messages.error(request, "You've asked for several emails already. Please try again in an hour.")
    else:
        record_attempt(key, 3600)
        send_verification_email(request, request.user)
        messages.success(request, f"We've sent a new confirmation link to {request.user.email}.")
    return redirect("accounts:dashboard")


class LoginView(auth_views.LoginView):
    """Blocks an IP and email pair for 15 minutes after 5 failed attempts."""

    template_name = "accounts/form_page.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True
    extra_context = {
        "title": "Sign in", "heading": "Your pass to the port", "submit_label": "Sign in and board",
        "intro": "Sign in to book sailings and see your tickets.", "after_form": "login",
    }

    def rate_key(self):
        email = self.request.POST.get("username", "").strip().lower()
        return f"login-fail:{client_ip(self.request)}:{email}"

    def post(self, request, *args, **kwargs):
        if is_rate_limited(self.rate_key(), LOGIN_FAILURE_LIMIT):
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, "Too many unsuccessful attempts. Please wait 15 minutes or reset your password.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        record_attempt(self.rate_key(), LOGIN_WINDOW_SECONDS)
        return super().form_invalid(form)


@login_required
def dashboard(request):
    memberships = request.user.operator_memberships.filter(is_active=True).select_related("operator")
    bookings = request.user.bookings.select_related("schedule__route__origin", "schedule__route__destination")
    return render(request, "accounts/dashboard.html", {"memberships": memberships, "bookings": bookings[:20]})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your details have been saved.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/form_page.html", {
        "form": form,
        "title": "Your details",
        "intro": f"Signed in as {request.user.email}. To change your email address, contact support.",
        "submit_label": "Save details",
    })


password_reset = auth_views.PasswordResetView.as_view(
    form_class=ResetForm,
    template_name="accounts/form_page.html",
    email_template_name="accounts/email/password_reset.txt",
    subject_template_name="accounts/email/password_reset_subject.txt",
    success_url=reverse_lazy("accounts:password_reset_done"),
    extra_context={
        "title": "Reset your password",
        "intro": "Enter the email you registered with. If it matches an account, we'll send a reset link.",
        "submit_label": "Send reset link",
    },
)
password_reset_done = auth_views.PasswordResetDoneView.as_view(
    template_name="accounts/message_page.html",
    extra_context={
        "title": "Check your email",
        "body": "If that email matches an account, a reset link is on its way. The link expires in 3 days and works once.",
    },
)
password_reset_confirm = auth_views.PasswordResetConfirmView.as_view(
    form_class=NewPasswordForm,
    template_name="accounts/password_reset_confirm.html",
    success_url=reverse_lazy("accounts:password_reset_complete"),
    extra_context={"title": "Choose a new password", "submit_label": "Save new password"},
)
password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/message_page.html",
    extra_context={"title": "Password changed", "body": "You can now sign in with your new password.",
                   "link_url": reverse_lazy("accounts:login"), "link_label": "Sign in"},
)
password_change = auth_views.PasswordChangeView.as_view(
    form_class=ChangePasswordForm,
    template_name="accounts/form_page.html",
    success_url=reverse_lazy("accounts:password_change_done"),
    extra_context={"title": "Change password", "submit_label": "Change password"},
)
password_change_done = auth_views.PasswordChangeDoneView.as_view(
    template_name="accounts/message_page.html",
    extra_context={"title": "Password changed", "body": "Your password has been updated.",
                   "link_url": reverse_lazy("accounts:dashboard"), "link_label": "Back to your account"},
)
logout = auth_views.LogoutView.as_view()
