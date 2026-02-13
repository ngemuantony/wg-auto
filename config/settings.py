import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── BASE DIR & ENV ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Try multiple paths for .env file
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    loaded = load_dotenv(dotenv_path)
    print(f"✓ Loaded .env from {dotenv_path} (success: {loaded})", file=sys.stderr)
else:
    print(f"✗ .env not found at {dotenv_path}", file=sys.stderr)
    # Also check parent directory
    alt_dotenv = BASE_DIR.parent / ".env"
    if alt_dotenv.exists():
        load_dotenv(alt_dotenv)
        print(f"✓ Loaded .env from {alt_dotenv}", file=sys.stderr)

# ── SECURITY ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key")

# Warn if using a weak or placeholder SECRET_KEY in non-development environments
if SECRET_KEY in ("changeme", "dev-secret-key", "devkey1234567890"):
    if not DEBUG:
        import warnings
        warnings.warn(
            f"WARNING: Using weak SECRET_KEY '{SECRET_KEY}' in production! "
            "Please set SECRET_KEY environment variable to a strong random value.",
            RuntimeWarning
        )
    print(f"WARNING: Using placeholder SECRET_KEY in settings", file=sys.stderr)

# Parse DEBUG as boolean - handle both string and integer values
debug_value = os.environ.get("DEBUG", "1").lower()
if debug_value in ("true", "1", "yes", "on"):
    DEBUG = True
elif debug_value in ("false", "0", "no", "off"):
    DEBUG = False
else:
    try:
        DEBUG = bool(int(debug_value))
    except ValueError:
        DEBUG = False

#ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
ALLOWED_HOSTS = ['*']

# ── APPLICATIONS ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "wireguard",
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

# ── DATABASE ─────────────────────────────────────────────────────────────────
db_name = os.environ.get("DATABASE_NAME", os.environ.get("POSTGRES_DB", "wg_auto_db"))
db_user = os.environ.get("DATABASE_USER", os.environ.get("POSTGRES_USER", "postgres"))
db_password = os.environ.get("DATABASE_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "postgres"))
db_host = os.environ.get("DATABASE_HOST", os.environ.get("POSTGRES_HOST", "127.0.0.1"))
db_port = int(os.environ.get("DATABASE_PORT", os.environ.get("POSTGRES_PORT", 5432)))

print(f"Database Config: user={db_user} host={db_host} port={db_port} db={db_name}", file=sys.stderr)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": db_user,
        "PASSWORD": db_password,
        "HOST": db_host,
        "PORT": db_port,
    }
}

# ── REDIS / CACHES ───────────────────────────────────────────────────────────
# Use the encoded URLs from environment variables
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://127.0.0.1:6379/0"  # fallback if not set
)
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND",
    CELERY_BROKER_URL
)

# Use the same broker URL for Django cache (just switch DB to 1 if needed)
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", CELERY_BROKER_URL.replace("/0", "/1"))

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

print("Using Redis cache URL:", REDIS_CACHE_URL)
print("Using Celery Broker:", CELERY_BROKER_URL)
print("Using Celery Result Backend:", CELERY_RESULT_BACKEND)


# ── ENCRYPTION / WIREGUARD ────────────────────────────────────────────────────
# ENCRYPTION_KEY must be a valid Fernet key (32 url-safe base64-encoded bytes)
# Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_encryption_key_value = os.environ.get("ENCRYPTION_KEY")

if _encryption_key_value:
    ENCRYPTION_KEY = _encryption_key_value.encode() if isinstance(_encryption_key_value, str) else _encryption_key_value
else:
    # Generate a default key if not provided (for development only)
    import sys
    from cryptography.fernet import Fernet
    ENCRYPTION_KEY = Fernet.generate_key()
    print(f"WARNING: ENCRYPTION_KEY not set. Generated a temporary key for this session.", file=sys.stderr)
    print(f"For production, set ENCRYPTION_KEY in .env with a persistent key:", file=sys.stderr)
    print(f"  ENCRYPTION_KEY={ENCRYPTION_KEY.decode()}", file=sys.stderr)

WIREGUARD_INTERFACE = os.environ.get("WIREGUARD_INTERFACE", "wg0")
WIREGUARD_ENDPOINT = os.environ.get("WIREGUARD_ENDPOINT", "127.0.0.1:51820")

# ── PASSWORD VALIDATORS ──────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── INTERNATIONALIZATION ─────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── STATIC FILES ─────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Create staticfiles directory if it doesn't exist
os.makedirs(STATIC_ROOT, exist_ok=True)
