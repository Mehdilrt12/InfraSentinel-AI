from datetime import timedelta
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [
        part.strip() for part in os.getenv(name, default).split(",") if part.strip()
    ]


def env_required(name):
    value = os.getenv(name)
    if value is None or value == "":
        raise ImproperlyConfigured(
            f"La variable d'environnement {name} est obligatoire."
        )
    return value


SECRET_KEY = env_required("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", env_required("ALLOWED_HOSTS"))
FRONTEND_URL = env_required("FRONTEND_URL")
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", env_required("CORS_ALLOWED_ORIGINS")
)
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", env_required("CSRF_TRUSTED_ORIGINS")
)
CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "corsheaders",
    "channels",
    "accounts",
    "inventory",
    "metrics",
    "monitoring",
    "ml_engine",
    "integrations",
    "notifications",
    "realtime",
    "async_tasks",
    "common",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.middleware.APISecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_ENGINE = os.getenv("DATABASE_ENGINE", "postgresql").lower()
if DATABASE_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_DB_PATH") or BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_required("POSTGRES_DB"),
            "USER": env_required("POSTGRES_USER"),
            "PASSWORD": env_required("POSTGRES_PASSWORD"),
            "HOST": env_required("POSTGRES_HOST"),
            "PORT": env_required("POSTGRES_PORT"),
            "OPTIONS": {"sslmode": os.getenv("POSTGRES_SSLMODE", "prefer")},
            "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
IS_TESTING = "test" in os.sys.argv
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if IS_TESTING
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
WHITENOISE_USE_FINDERS = DEBUG or IS_TESTING
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("common.permissions.IsActiveTenant",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "2000/hour",
        "auth_login_ip": os.getenv("AUTH_LOGIN_IP_RATE", "10/min"),
        "auth_login_account": os.getenv("AUTH_LOGIN_ACCOUNT_RATE", "5/min"),
        "registration": os.getenv("REGISTRATION_RATE", "5/hour"),
        "agent_enrollment": os.getenv("AGENT_ENROLLMENT_RATE", "10/min"),
        "agent_request": os.getenv("AGENT_REQUEST_RATE", "120/min"),
    },
    # Trust the socket peer by default. A production reverse proxy may set this to
    # its exact hop count after it has stripped client-supplied forwarding headers.
    "NUM_PROXIES": int(os.getenv("TRUSTED_PROXY_COUNT", "0")),
}
API_DOCS_PUBLIC = env_bool("API_DOCS_PUBLIC", DEBUG)
PUBLIC_REGISTRATION_ENABLED = env_bool("PUBLIC_REGISTRATION_ENABLED", False)
SPECTACULAR_SETTINGS = {
    "TITLE": "InfraSentinel AI API",
    "DESCRIPTION": (
        "API centrale multi-tenant de supervision Windows, VMware et Hyper-V. "
        "Les routes protegees utilisent un JWT Bearer ou une session Django; "
        "les routes agent utilisent un jeton d'agent dedie."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PUBLIC": True,
    "SERVE_AUTHENTICATION": [] if API_DOCS_PUBLIC else None,
    "SERVE_PERMISSIONS": (
        ["rest_framework.permissions.AllowAny"]
        if API_DOCS_PUBLIC
        else ["common.permissions.IsAdmin"]
    ),
    "SCHEMA_PATH_PREFIX": r"/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "displayOperationId": True,
        "persistAuthorization": False,
        "filter": True,
    },
    "ENUM_NAME_OVERRIDES": {
        "EnvironmentTypeEnum": "inventory.models.Environment.Kind",
        "IntegrationSourceEnum": "inventory.models.IntegrationEndpoint.Kind",
        "VirtualAssetTypeEnum": "inventory.models.VirtualAsset.Kind",
        "MonitoringSeverityEnum": "monitoring.models.Severity",
        "AsyncExecutionStatusEnum": "async_tasks.models.TaskRun.Status",
    },
    "TAGS": [
        {
            "name": "Authentication",
            "description": "Connexion, inscription et profil courant.",
        },
        {"name": "Users", "description": "Administration des comptes utilisateurs."},
        {"name": "Customers", "description": "Administration des tenants clients."},
        {
            "name": "Environments",
            "description": "Environnements Windows, VMware et Hyper-V.",
        },
        {
            "name": "Agents",
            "description": "Gestion, enrôlement et communications des agents Windows.",
        },
        {"name": "Machines", "description": "Inventaire centralisé des machines."},
        {
            "name": "Metrics",
            "description": "Métriques normalisées et agrégats historiques.",
        },
        {"name": "Rules", "description": "Règles configurables de supervision."},
        {"name": "Alerts", "description": "Alertes centralisées et cycle de vie."},
        {"name": "Anomalies", "description": "Anomalies détectées par le moteur ML."},
        {
            "name": "Predictions",
            "description": "Analyses de tendances fondées sur l'historique réel.",
        },
        {
            "name": "ML",
            "description": "Versions, entraînement et évaluation des modèles.",
        },
        {"name": "VMware", "description": "Connecteurs et inventaire VMware/vCenter."},
        {
            "name": "Hyper-V",
            "description": "Connecteurs et inventaire Microsoft Hyper-V.",
        },
        {
            "name": "Notifications",
            "description": "Préférences et livraisons de notifications.",
        },
        {"name": "Dashboard", "description": "Synthèse opérationnelle multi-tenant."},
        {
            "name": "Realtime",
            "description": "Tickets WebSocket et reprise d'événements.",
        },
        {
            "name": "Operations",
            "description": "Audit, collectes, tâches et rapports asynchrones.",
        },
        {"name": "System", "description": "État de santé de l'API."},
    ],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "agentToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Agent-Token",
                "description": (
                    "Jeton opaque retourné une seule fois lors de l'enrôlement. "
                    "Authorization: Bearer <jeton> est également accepté par l'implémentation."
                ),
            }
        }
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env_required("JWT_SIGNING_KEY"),
    "AUDIENCE": os.getenv("JWT_AUDIENCE", "infrasentinel-clients"),
    "ISSUER": os.getenv("JWT_ISSUER", "infrasentinel-api"),
    "USER_AUTHENTICATION_RULE": "common.auth_api.active_user_authentication_rule",
}

JWT_REFRESH_COOKIE_NAME = os.getenv(
    "JWT_REFRESH_COOKIE_NAME", "infrasentinel_refresh"
)
JWT_REFRESH_COOKIE_SECURE = env_bool("JWT_REFRESH_COOKIE_SECURE", not DEBUG)
JWT_REFRESH_COOKIE_SAMESITE = os.getenv("JWT_REFRESH_COOKIE_SAMESITE", "Strict")
JWT_REFRESH_COOKIE_PATH = "/api/auth/browser/"
if JWT_REFRESH_COOKIE_SAMESITE not in {"Strict", "Lax", "None"}:
    raise ImproperlyConfigured("JWT_REFRESH_COOKIE_SAMESITE est invalide.")
if JWT_REFRESH_COOKIE_SAMESITE == "None" and not JWT_REFRESH_COOKIE_SECURE:
    raise ImproperlyConfigured("SameSite=None exige un cookie refresh Secure.")

REDIS_URL = env_required("REDIS_URL")
if IS_TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "infrasentinel-tests",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("CACHE_URL", REDIS_URL),
            "KEY_PREFIX": "infrasentinel",
            "TIMEOUT": 300,
        }
    }
if os.getenv("CHANNEL_LAYER", "redis") == "memory" or "test" in os.sys.argv:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL], "capacity": 1500, "expiry": 60},
        }
    }

CELERY_BROKER_URL = env_required("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env_required("CELERY_RESULT_BACKEND")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "900"))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "840"))
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = 86400
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ROUTES = {
    "integrations.collect_hyperv_connector": {"queue": "hyperv"},
}
CELERY_BEAT_SCHEDULE = {
    "evaluate-rules-every-minute": {
        "task": "monitoring.evaluate_rules",
        "schedule": 60.0,
    },
    "analyze-ml-every-five-minutes": {"task": "ml.analyze_recent", "schedule": 300.0},
    "notifications-every-15-seconds": {
        "task": "notifications.dispatch_pending",
        "schedule": 15.0,
    },
    "collect-vmware-every-five-minutes": {
        "task": "integrations.collect_vmware",
        "schedule": 300.0,
    },
    "collect-hyperv-every-five-minutes": {
        "task": "integrations.collect_hyperv",
        "schedule": 300.0,
    },
    "aggregate-history-hourly": {
        "task": "metrics.aggregate_history",
        "schedule": 3600.0,
    },
}

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "InfraSentinel <noreply@localhost>"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))

NOTIFICATION_SENDING_TIMEOUT_SECONDS = int(
    os.getenv("NOTIFICATION_SENDING_TIMEOUT_SECONDS", "300")
)
ML_MODEL_DIR = os.getenv("ML_MODEL_DIR") or str(BASE_DIR / "model_store")

if env_bool("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(2_621_440))
)
FILE_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(2_621_440))
)

CONNECTOR_ALLOWED_HOSTS = env_list("CONNECTOR_ALLOWED_HOSTS", "")
ALLOW_INSECURE_CONNECTOR_TLS = env_bool("ALLOW_INSECURE_CONNECTOR_TLS", False)
WEBSOCKET_SESSION_MAX_SECONDS = int(
    os.getenv("WEBSOCKET_SESSION_MAX_SECONDS", "900")
)
if not 60 <= WEBSOCKET_SESSION_MAX_SECONDS <= 86_400:
    raise ImproperlyConfigured("WEBSOCKET_SESSION_MAX_SECONDS doit valoir 60 à 86400.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "()": "common.logging_utils.RedactingFormatter",
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"}
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
