"""Ship Booking settings. Every environment-specific value comes from env vars (see .env.example)."""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required environment variable {name}")
    return value


def env_bool(name, default=False):
    return env(name, str(default)).lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.operators",
    "apps.fleet",
    "apps.schedules",
    "apps.bookings",
    "apps.payments",
    "apps.tickets",
    "apps.support",
    "apps.compliance",
    "apps.pages",
    "apps.staff",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.pages.seo.NoIndexPrivateMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.pages.context_processors.site",
                "apps.compliance.views.consent",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Supabase Postgres when DATABASE_URL is set (direct connection or session pooler, port 5432;
# not the 6543 transaction pooler). Falls back to SQLite for offline work.
DATABASE_URL = env("DATABASE_URL", "")
if DATABASE_URL:
    db_url = urlsplit(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_url.path.lstrip("/") or "postgres",
            "USER": unquote(db_url.username or ""),
            "PASSWORD": unquote(db_url.password or ""),
            "HOST": db_url.hostname,
            "PORT": db_url.port or 5432,
            "OPTIONS": {"sslmode": env("DB_SSLMODE", "require")},
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            "ATOMIC_REQUESTS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("SQLITE_PATH", "") or str(BASE_DIR / "db.sqlite3"),
            "ATOMIC_REQUESTS": True,
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "pages:home"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Stored in UTC, displayed in India time.
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

MAILERS = {
    "default": {
        "BACKEND": env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"),
    },
}
if MAILERS["default"]["BACKEND"].endswith("smtp.EmailBackend"):
    MAILERS["default"]["OPTIONS"] = {
        "host": env("EMAIL_HOST"),
        "port": int(env("EMAIL_PORT", "587")),
        "username": env("EMAIL_HOST_USER", ""),
        "password": env("EMAIL_HOST_PASSWORD", ""),
        "use_tls": env_bool("EMAIL_USE_TLS", True),
        "timeout": 10,
    }
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@localhost")
# Absolute links in emails and on e-ticket QR codes.
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")

# Sessions and cookies
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"  # Razorpay may open bank/UPI pop-ups

# Content Security Policy. Scripts only from this site and Razorpay checkout; the one inline script
# (payment page) carries a per-request nonce. Inline style attributes are allowed (low risk, used widely).
RAZORPAY_HOSTS = ["https://checkout.razorpay.com", "https://api.razorpay.com", "https://*.razorpay.com"]
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE, *RAZORPAY_HOSTS],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:", *RAZORPAY_HOSTS],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF, *RAZORPAY_HOSTS],
    "frame-src": RAZORPAY_HOSTS,
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF, *RAZORPAY_HOSTS],
    "base-uri": [CSP.SELF],
    "object-src": [CSP.NONE],
}

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # Versioned file names (site.abc123.css) so browsers never keep a stale stylesheet after a deploy.
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }

# People emailed the full traceback when a page crashes in production ("Name <email>,Name <email>").
ADMINS = [a.strip() for a in env("DJANGO_ADMINS", "").split(",") if a.strip()]
SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        "json": {"()": "config.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": env("LOG_FORMAT", "plain")},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR", "filters": ["prod_only"]},
    },
    "filters": {"prod_only": {"()": "django.utils.log.RequireDebugFalse"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"handlers": ["console", "mail_admins"], "level": "ERROR", "propagate": False}},
}

# Booking platform
CURRENCY = "INR"
INVENTORY_HOLD_MINUTES = int(env("INVENTORY_HOLD_MINUTES", "15"))

# Payments: sandbox only until the live-payment gate in the spec is satisfied.
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", "razorpay")
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
PAYMENTS_LIVE_MODE = env_bool("PAYMENTS_LIVE_MODE", False)
if PAYMENTS_LIVE_MODE and RAZORPAY_KEY_ID.startswith("rzp_test_"):
    raise ImproperlyConfigured("PAYMENTS_LIVE_MODE is on but a Razorpay test key is configured.")
if not PAYMENTS_LIVE_MODE and RAZORPAY_KEY_ID.startswith("rzp_live_"):
    raise ImproperlyConfigured("A live Razorpay key is configured but PAYMENTS_LIVE_MODE is off. Use test keys.")

# Business facts that must be supplied and verified before launch. Empty = shown as "not yet configured".
BUSINESS = {
    "legal_entity_name": env("BUSINESS_LEGAL_ENTITY_NAME", ""),
    "registered_address": env("BUSINESS_REGISTERED_ADDRESS", ""),
    "support_email": env("BUSINESS_SUPPORT_EMAIL", ""),
    "support_phone": env("BUSINESS_SUPPORT_PHONE", ""),
    "grievance_officer_name": env("BUSINESS_GRIEVANCE_OFFICER_NAME", ""),
    "grievance_officer_email": env("BUSINESS_GRIEVANCE_OFFICER_EMAIL", ""),
    # One of: intermediary, marketplace, operator. Must be stated accurately on public pages.
    "platform_role": env("BUSINESS_PLATFORM_ROLE", ""),
}

# Retention periods in days. These are business decisions: confirm them with legal review before launch.
RETENTION = {
    "abandoned_booking_days": int(env("RETENTION_ABANDONED_BOOKING_DAYS", "30")),
    "notification_days": int(env("RETENTION_NOTIFICATION_DAYS", "180")),
    "anonymous_cookie_days": int(env("RETENTION_ANONYMOUS_COOKIE_DAYS", "365")),
}
COOKIE_CONSENT_DAYS = int(env("COOKIE_CONSENT_DAYS", "365"))

# Real client IP header set by the reverse proxy (e.g. HTTP_X_REAL_IP). Empty = use REMOTE_ADDR (no proxy).
TRUSTED_PROXY_HEADER = env("TRUSTED_PROXY_HEADER", "")

# Shared by every worker so rate limits hold across processes. Create with: manage.py createcachetable
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_table"}}
