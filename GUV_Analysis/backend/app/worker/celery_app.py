from celery import Celery
from app.core.config import settings

print(f"DEBUG: Initializing Celery with broker={settings.CELERY_BROKER_URL}")

celery_app = Celery("worker", broker=settings.CELERY_BROKER_URL)

# Auto-discover tasks in the worker module
celery_app.autodiscover_tasks(['app.worker'])

# celery_app.conf.task_routes = {
#     "app.worker.tasks.run_analysis_task": "main-queue"
# }
celery_app.conf.update(
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
