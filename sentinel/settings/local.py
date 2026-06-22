from pathlib import Path

from .base import *

DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(Path(BASE_DIR) / "db.sqlite3"),
    }
}
REDIS_URL = "redis://127.0.0.1:6379/0"
SENTINEL_ENGINE_URL = "http://127.0.0.1:8081"
CHANNEL_LAYERS["default"]["CONFIG"]["hosts"] = [REDIS_URL]
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
