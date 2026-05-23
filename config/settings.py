import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def validate_production_settings(
    *,
    environment: str,
    debug: bool,
    secret_key: str,
    secret_key_configured: bool,
    allowed_hosts: list[str],
    allowed_hosts_configured: bool,
    database_engine: str,
    auth_provider: str,
    enable_dev_auth: bool,
    session_cookie_secure: bool,
    csrf_cookie_secure: bool,
    secure_ssl_redirect: bool,
    secure_proxy_ssl_header: tuple[str, str] | None,
) -> None:
    if environment != "production":
        return

    errors: list[str] = []
    unsafe_secret_keys = {"", "unsafe-dev-secret-key", "change-me"}
    if debug:
        errors.append("TSMS_DEBUG must be false when TSMS_ENVIRONMENT=production")
    if not secret_key_configured or secret_key in unsafe_secret_keys:
        errors.append("TSMS_SECRET_KEY must be set to a non-development secret")
    if not allowed_hosts_configured or not allowed_hosts:
        errors.append("TSMS_ALLOWED_HOSTS must be set explicitly")
    if "*" in allowed_hosts:
        errors.append("TSMS_ALLOWED_HOSTS must not contain '*'")
    if database_engine != "django.db.backends.postgresql":
        errors.append("TSMS_DB_BACKEND must be postgres in production")
    if auth_provider == "development-email" or enable_dev_auth:
        errors.append("development email login must be disabled in production")
    if not session_cookie_secure:
        errors.append("TSMS_SESSION_COOKIE_SECURE must be true in production")
    if not csrf_cookie_secure:
        errors.append("TSMS_CSRF_COOKIE_SECURE must be true in production")
    if not secure_ssl_redirect:
        errors.append("TSMS_SECURE_SSL_REDIRECT must be true in production")
    if secure_proxy_ssl_header is None:
        errors.append("TSMS_ENABLE_PROXY_SSL_HEADER must be true in production")

    if errors:
        raise ImproperlyConfigured(
            "Production settings are invalid: " + "; ".join(errors)
        )


def build_database_config() -> dict[str, object]:
    backend = os.getenv("TSMS_DB_BACKEND", "sqlite").strip().lower()
    if backend == "postgres":
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("TSMS_DB_NAME", "tsms"),
            "USER": os.getenv("TSMS_DB_USER", "tsms"),
            "PASSWORD": os.getenv("TSMS_DB_PASSWORD", "tsms"),
            "HOST": os.getenv("TSMS_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("TSMS_DB_PORT", "5432"),
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


TSMS_ENVIRONMENT = os.getenv("TSMS_ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = TSMS_ENVIRONMENT == "production"
SECRET_KEY = os.getenv("TSMS_SECRET_KEY", "" if IS_PRODUCTION else "unsafe-dev-secret-key")
DEBUG = env_bool("TSMS_DEBUG", not IS_PRODUCTION)
TSMS_AUTH_PROVIDER = os.getenv(
    "TSMS_AUTH_PROVIDER",
    "trusted-header" if IS_PRODUCTION else "development-email",
).strip()
TSMS_ENABLE_DEV_AUTH = env_bool("TSMS_ENABLE_DEV_AUTH", not IS_PRODUCTION)
TSMS_TRUSTED_EMAIL_HEADER = os.getenv(
    "TSMS_TRUSTED_EMAIL_HEADER",
    "HTTP_X_MS_CLIENT_PRINCIPAL_NAME",
).strip()
ALLOWED_HOSTS = env_list(
    "TSMS_ALLOWED_HOSTS",
    "" if IS_PRODUCTION else "127.0.0.1,localhost",
)
CSRF_TRUSTED_ORIGINS = env_list("TSMS_CSRF_TRUSTED_ORIGINS")
SESSION_COOKIE_SECURE = env_bool("TSMS_SESSION_COOKIE_SECURE", IS_PRODUCTION)
CSRF_COOKIE_SECURE = env_bool("TSMS_CSRF_COOKIE_SECURE", IS_PRODUCTION)
SECURE_SSL_REDIRECT = env_bool("TSMS_SECURE_SSL_REDIRECT", IS_PRODUCTION)
SECURE_HSTS_SECONDS = env_int("TSMS_SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("TSMS_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("TSMS_SECURE_HSTS_PRELOAD", False)
SECURE_PROXY_SSL_HEADER = (
    (
        os.getenv("TSMS_SECURE_PROXY_SSL_HEADER_NAME", "HTTP_X_FORWARDED_PROTO").strip(),
        os.getenv("TSMS_SECURE_PROXY_SSL_HEADER_VALUE", "https").strip(),
    )
    if env_bool("TSMS_ENABLE_PROXY_SSL_HEADER", IS_PRODUCTION)
    else None
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.auth",
    "apps.core",
    "apps.reference_data",
    "apps.master_data",
    "apps.timesheets",
    "apps.integrations",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.auth.middleware.InternalSessionMiddleware",
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
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": build_database_config()}

validate_production_settings(
    environment=TSMS_ENVIRONMENT,
    debug=DEBUG,
    secret_key=SECRET_KEY,
    secret_key_configured="TSMS_SECRET_KEY" in os.environ,
    allowed_hosts=ALLOWED_HOSTS,
    allowed_hosts_configured="TSMS_ALLOWED_HOSTS" in os.environ,
    database_engine=DATABASES["default"]["ENGINE"],  # type: ignore[index]
    auth_provider=TSMS_AUTH_PROVIDER,
    enable_dev_auth=TSMS_ENABLE_DEV_AUTH,
    session_cookie_secure=SESSION_COOKIE_SECURE,
    csrf_cookie_secure=CSRF_COOKIE_SECURE,
    secure_ssl_redirect=SECURE_SSL_REDIRECT,
    secure_proxy_ssl_header=SECURE_PROXY_SSL_HEADER,
)

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("TSMS_LOG_LEVEL", "INFO"),
    },
}
