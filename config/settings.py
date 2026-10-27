"""Django settings for LawHub.

Configuration comes from environment variables so the same settings work
locally (SQLite, DEBUG) and in production (Postgres via DATABASE_URL).
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Public base URL, used for OAuth/MCP metadata and absolute links.
LAWHUB_PUBLIC_URL = os.environ.get("LAWHUB_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
CSRF_TRUSTED_ORIGINS = [LAWHUB_PUBLIC_URL]
if not DEBUG:
    # Hosting platforms terminate TLS at their proxy.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

# Private beta: every page needs a login and only allowlisted emails may sign up.
LAWHUB_PRIVATE = os.environ.get("LAWHUB_PRIVATE", "0") == "1"
LAWHUB_SIGNUP_ALLOWLIST = {e.strip().lower() for e in os.environ.get("LAWHUB_SIGNUP_ALLOWLIST", "").split(",") if e.strip()}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "oauth2_provider",
    "laws",
    "tags",
    "accounts",
    "connect",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    *(["django.contrib.auth.middleware.LoginRequiredMiddleware"] if LAWHUB_PRIVATE else []),
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'data' / 'lawhub.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
if "-pooler." in DATABASES["default"].get("HOST", ""):
    # Neon's pooled endpoint runs PgBouncer in transaction mode, which can't
    # keep server-side cursors open across queries.
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:subscriptions"
LOGOUT_REDIRECT_URL = "laws:home"

# OAuth for AI apps connecting over MCP (see connect/).
OAUTH2_PROVIDER = {
    "SCOPES": {"lawhub": "Czytanie przepisów i zarządzanie obserwowanymi tematami"},
    "DEFAULT_SCOPES": ["lawhub"],
    "PKCE_REQUIRED": True,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,
    "ROTATE_REFRESH_TOKEN": True,
}

# The law corpus: a separate git repository written by the importer.
LAWHUB_LAW_REPO = Path(os.environ.get("LAWHUB_LAW_REPO", BASE_DIR / "data" / "law-repo"))
# Local checkout of https://github.com/nalegaluorg/nalegalu (beta data source).
LAWHUB_NALEGALU = os.environ.get("LAWHUB_NALEGALU", "")
