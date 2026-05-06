from __future__ import annotations

from django.core.management.utils import get_random_secret_key

from config.env import ROOT_DIR, env_bool, env_int, env_list, env_str

ENV_NAME = env_str("APP_ENV", default="local")
DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = env_str("DJANGO_SECRET_KEY", default=get_random_secret_key())
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://127.0.0.1:8000",
)


def build_database_config() -> dict[str, dict[str, object]]:
    db_engine = env_str("DJANGO_DB_ENGINE", default="sqlite")

    if db_engine == "postgres":
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env_str("POSTGRES_DB", default="learning_site"),
                "USER": env_str("POSTGRES_USER", default="learning_site"),
                "PASSWORD": env_str("POSTGRES_PASSWORD", default="learning_site"),
                "HOST": env_str("POSTGRES_HOST", default="localhost"),
                "PORT": env_int("POSTGRES_PORT", default=5432),
            }
        }

    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ROOT_DIR / "db.sqlite3",
        }
    }


def build_cache_config() -> dict[str, dict[str, object]]:
    redis_url = env_str("REDIS_URL", default="")
    if redis_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
            }
        }

    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "learning-site-stage1",
        }
    }


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts.apps.AccountsConfig",
    "apps.diagnostic_handoff.apps.DiagnosticHandoffConfig",
    "apps.curriculum.apps.CurriculumConfig",
    "apps.resources.apps.ResourcesConfig",
    "apps.media_library.apps.MediaLibraryConfig",
    "apps.commerce.apps.CommerceConfig",
    "apps.access_control.apps.AccessControlConfig",
    "apps.learning_state.apps.LearningStateConfig",
    "apps.homework.apps.HomeworkConfig",
    "apps.operator.apps.OperatorConfig",
    "apps.events.apps.EventsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.shared.apps.SharedConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ROOT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = build_database_config()
CACHES = build_cache_config()

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = ROOT_DIR / "staticfiles"
STATICFILES_DIRS = [ROOT_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = ROOT_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", default=env_str("REDIS_URL", default=""))
CELERY_RESULT_BACKEND = env_str(
    "CELERY_RESULT_BACKEND",
    default=env_str("REDIS_URL", default=""),
)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = env_bool("CELERY_TASK_EAGER_PROPAGATES", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": env_str("DJANGO_LOG_LEVEL", default="INFO"),
    },
}
