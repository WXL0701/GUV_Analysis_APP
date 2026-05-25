import logging
import os
from celery import Celery
from app.core.config import settings

def _add_file_handler(logger: logging.Logger, filename: str, formatter: logging.Formatter, level: int) -> None:
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == filename:
            return
    handler = logging.FileHandler(filename)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _setup_worker_logging() -> None:
    log_dir = os.path.join(settings.RUN_BASE_DIR, "system_logs")
    os.makedirs(log_dir, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    worker_log = os.path.join(log_dir, "worker.log")
    root_logger = logging.getLogger()
    if root_logger.level == logging.WARNING:
        root_logger.setLevel(logging.INFO)
    _add_file_handler(root_logger, worker_log, formatter, logging.INFO)
    _add_file_handler(logging.getLogger("celery"), worker_log, formatter, logging.INFO)


_setup_worker_logging()

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
