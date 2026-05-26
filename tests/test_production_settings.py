import pytest
from django.core.exceptions import ImproperlyConfigured

from config import settings


def _valid_production_settings(**overrides):
    values = {
        "environment": "production",
        "debug": False,
        "secret_key": "production-secret-key-with-enough-entropy",
        "secret_key_configured": True,
        "allowed_hosts": ["tsms.example.com"],
        "allowed_hosts_configured": True,
        "database_engine": "django.db.backends.postgresql",
        "auth_provider": "trusted-header",
        "enable_dev_auth": False,
        "session_cookie_secure": True,
        "csrf_cookie_secure": True,
        "secure_ssl_redirect": True,
        "secure_proxy_ssl_header": ("HTTP_X_FORWARDED_PROTO", "https"),
    }
    values.update(overrides)
    return values


def test_validate_production_settings_accepts_complete_production_config() -> None:
    settings.validate_production_settings(**_valid_production_settings())


def test_validate_production_settings_ignores_development_config() -> None:
    settings.validate_production_settings(
        **_valid_production_settings(
            environment="development",
            debug=True,
            secret_key="unsafe-dev-secret-key",
            secret_key_configured=False,
            allowed_hosts=[],
            allowed_hosts_configured=False,
            database_engine="django.db.backends.sqlite3",
            auth_provider="development-email",
            enable_dev_auth=True,
            session_cookie_secure=False,
            csrf_cookie_secure=False,
            secure_ssl_redirect=False,
            secure_proxy_ssl_header=None,
        )
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"debug": True}, "TSMS_DEBUG must be false"),
        ({"secret_key": "unsafe-dev-secret-key"}, "TSMS_SECRET_KEY must be set"),
        ({"secret_key_configured": False}, "TSMS_SECRET_KEY must be set"),
        ({"allowed_hosts": []}, "TSMS_ALLOWED_HOSTS must be set"),
        ({"allowed_hosts_configured": False}, "TSMS_ALLOWED_HOSTS must be set"),
        ({"allowed_hosts": ["*"]}, "TSMS_ALLOWED_HOSTS must not contain '*'"),
        ({"database_engine": "django.db.backends.sqlite3"}, "TSMS_DB_BACKEND must be postgres"),
        ({"auth_provider": "development-email"}, "development email login"),
        ({"enable_dev_auth": True}, "development email login"),
        ({"session_cookie_secure": False}, "TSMS_SESSION_COOKIE_SECURE must be true"),
        ({"csrf_cookie_secure": False}, "TSMS_CSRF_COOKIE_SECURE must be true"),
        ({"secure_ssl_redirect": False}, "TSMS_SECURE_SSL_REDIRECT must be true"),
        ({"secure_proxy_ssl_header": None}, "TSMS_ENABLE_PROXY_SSL_HEADER must be true"),
    ],
)
def test_validate_production_settings_rejects_unsafe_production_config(
    override: dict,
    message: str,
) -> None:
    with pytest.raises(ImproperlyConfigured, match=message):
        settings.validate_production_settings(**_valid_production_settings(**override))


def test_build_database_config_uses_postgres_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSMS_DB_BACKEND", "postgres")
    monkeypatch.setenv("TSMS_DB_NAME", "prod-tsms")
    monkeypatch.setenv("TSMS_DB_USER", "prod-user")
    monkeypatch.setenv("TSMS_DB_PASSWORD", "prod-password")
    monkeypatch.setenv("TSMS_DB_HOST", "prod-host.postgres.database.azure.com")
    monkeypatch.setenv("TSMS_DB_PORT", "5432")

    database_config = settings.build_database_config()

    assert database_config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "prod-tsms",
        "USER": "prod-user",
        "PASSWORD": "prod-password",
        "HOST": "prod-host.postgres.database.azure.com",
        "PORT": "5432",
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": "require"},
    }


def test_build_database_config_allows_database_runtime_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TSMS_DB_BACKEND", "postgres")
    monkeypatch.setenv("TSMS_DB_CONN_MAX_AGE", "120")
    monkeypatch.setenv("TSMS_DB_SSLMODE", "verify-full")

    database_config = settings.build_database_config()

    assert database_config["CONN_MAX_AGE"] == 120
    assert database_config["OPTIONS"] == {"sslmode": "verify-full"}


def test_build_database_config_can_disable_postgres_sslmode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TSMS_DB_BACKEND", "postgres")
    monkeypatch.setenv("TSMS_DB_SSLMODE", "")

    database_config = settings.build_database_config()

    assert "OPTIONS" not in database_config


def test_env_list_parses_comma_separated_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TSMS_CSRF_TRUSTED_ORIGINS",
        "https://tsms.example.com, https://tsms.azurewebsites.net",
    )

    assert settings.env_list("TSMS_CSRF_TRUSTED_ORIGINS") == [
        "https://tsms.example.com",
        "https://tsms.azurewebsites.net",
    ]


def test_static_runtime_uses_development_storage_by_default() -> None:
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE
    assert settings.STORAGES["staticfiles"] == {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }


def test_static_runtime_uses_whitenoise_storage_for_production() -> None:
    assert settings.build_staticfiles_storage_backend(is_production=True) == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )


def test_static_runtime_allows_storage_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSMS_STATICFILES_STORAGE", "example.StaticStorage")

    assert settings.build_staticfiles_storage_backend(is_production=True) == "example.StaticStorage"


def test_static_runtime_ignores_blank_storage_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSMS_STATICFILES_STORAGE", "")

    assert settings.build_staticfiles_storage_backend(is_production=False) == (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


def test_static_root_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSMS_STATIC_ROOT", "/tmp/tsms-staticfiles")

    assert str(settings.build_static_root()) == "/tmp/tsms-staticfiles"
