"""Django settings for Tradewind.

Secrets and anything that differs between a laptop and a real server come
from environment variables, never from this file.
"""

import os
from pathlib import Path

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

# SQLite by default. "IMMEDIATE" makes each transaction take the write lock at the
# start, so two checkouts can't both read "1 left" and both buy it.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("TRADEWIND_SQLITE_PATH", BASE_DIR / "tradewind.db"),
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 30},
        "TEST": {"NAME": BASE_DIR / "test-tradewind.db"},   # a real file, so tests can use several threads
    }
}

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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "catalogue"
LOGOUT_REDIRECT_URL = "catalogue"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:                                  # on a real server, cookies only travel over HTTPS
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

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
