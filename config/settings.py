"""Django settings for Tradewind.

Secrets and anything that differs between a laptop and a real server come
from environment variables, never from this file.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("TRADEWIND_DEBUG", "1") == "1"

# A fixed key is fine for local development; a real deployment must set its own.
SECRET_KEY = os.environ.get("TRADEWIND_SECRET_KEY") or (
    "dev-only-insecure-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set TRADEWIND_SECRET_KEY when TRADEWIND_DEBUG is off")

ALLOWED_HOSTS = os.environ.get("TRADEWIND_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shop.middleware.SecurityHeaders",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context.shop",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite by default (one file, nothing to install). Set TRADEWIND_DATABASE_URL to use PostgreSQL,
# e.g. postgresql://user:password@localhost:5432/tradewind
DATABASE_URL = os.environ.get("TRADEWIND_DATABASE_URL", "")


def _database(url):
    if not url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("TRADEWIND_SQLITE_PATH", BASE_DIR / "tradewind.db"),
            # IMMEDIATE takes the write lock when a transaction starts, so two checkouts
            # can't both read "1 left" and both buy it (PostgreSQL uses row locks instead)
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 30},
            "TEST": {"NAME": BASE_DIR / "test-tradewind.db"},   # a real file, so tests can use threads
        }
    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("TRADEWIND_DATABASE_URL must start with postgresql://")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": u.path.lstrip("/"),
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname or "",
        "PORT": str(u.port or ""),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }


DATABASES = {"default": _database(DATABASE_URL)}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "America/St_Vincent"
USE_I18N = True
USE_TZ = True                      # store times in UTC, show them in local time

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"     # `collectstatic` gathers files here for a real web server
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "catalogue"
LOGOUT_REDIRECT_URL = "catalogue"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    # On a real server: HTTPS only, and tell browsers to remember that
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get("TRADEWIND_SSL_REDIRECT", "1") == "1"
    SECURE_HSTS_SECONDS = int(os.environ.get("TRADEWIND_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("127.0.0.1", "localhost")]

# ---- Shop settings ------------------------------------------------------------
SHOP_NAME = "Tradewind"
CURRENCY = "EC$"
DELIVERY_FEE_CENTS = 2500                  # EC$25.00, VAT included
FREE_DELIVERY_FROM_CENTS = 30000           # free delivery on orders of EC$300 or more
UNPAID_ORDER_DAYS = {"collection": 2, "bank_transfer": 3}   # unpaid orders are cancelled after this
# Shown to customers who choose bank transfer. These are made-up demo details, not a real account.
BANK_DETAILS = {
    "bank": "Demo Bank (not a real account)",
    "account_name": "Tradewind Demo Shop",
    "account_number": "000-DEMO-0000",
    "note": "Put your order number as the payment reference.",
}
