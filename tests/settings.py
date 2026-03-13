"""
Minimal Django settings for running django-whoop tests.
"""

SECRET_KEY = "django-whoop-test-secret-key-not-for-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django_whoop",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

# django_whoop/apps.py sets label = 'whoop', so migrations live under that label
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Include the app's own templates directory so whoop/login.html etc. resolve.
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    }
]

ROOT_URLCONF = "tests.urls"
