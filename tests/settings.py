import os

SECRET_KEY = "local-tests-only"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "vatly_django",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql"
        if os.getenv("PGHOST")
        else "django.db.backends.sqlite3",
        "NAME": os.getenv("PGDATABASE", ":memory:"),
        "USER": os.getenv("PGUSER", ""),
        "PASSWORD": os.getenv("PGPASSWORD", ""),
        "HOST": os.getenv("PGHOST", ""),
    }
}
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
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
ROOT_URLCONF = "vatly_django.urls"
ALLOWED_HOSTS = ["testserver"]
USE_TZ = True
VATLY_API_KEY = "test_" + "x" * 20
VATLY_SCOPE = "tenant/storefront"
VATLY_WEBHOOK_SECRET = "test-signing-secret"
VATLY_REDIRECT_URL_SUCCESS = "https://app.test/success"
VATLY_REDIRECT_URL_CANCELED = "https://app.test/canceled"
VATLY_PORTAL_REDIRECT_URL = "https://app.test/billing"
VATLY_CHECKOUTS = {"book": {"products": [{"id": "one_off_product_test", "quantity": 1}]}}
