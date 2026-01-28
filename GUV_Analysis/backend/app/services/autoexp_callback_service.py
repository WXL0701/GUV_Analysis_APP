import json
import logging
import time
from typing import Any, Dict, Optional

import urllib3
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Task, TaskRun, User

logger = logging.getLogger(__name__)

_http = urllib3.PoolManager(
    timeout=urllib3.Timeout(connect=settings.AUTOEXP_CALLBACK_TIMEOUT_SECONDS, read=settings.AUTOEXP_CALLBACK_TIMEOUT_SECONDS),
    retries=False,
)


def _is_external_task(db: Session, task: Task) -> bool:
    if not task.user_id:
        return False
    user = db.query(User).filter(User.id == task.user_id).first()
    if not user:
        return False
    return user.role == "external"


def _build_payload(
    *,
    task: Task,
    task_run: Optional[TaskRun],
    mode: Optional[str],
    run_dir: Optional[str],
    error_code: Optional[str],
    error_message: Optional[str],
) -> Dict[str, Any]:
    success = task.status == "SUCCEEDED"
    payload: Dict[str, Any] = {
        "taskId": str(task.id),
        "success": bool(success),
        "data": {
            "run_id": str(task_run.id) if task_run and task_run.id else (str(task.run_id_current) if task.run_id_current else None),
            "run_mode": str(mode) if mode else (str(task_run.run_mode) if task_run and task_run.run_mode else None),
            "status": str(task.status),
            "task_type": "external_autorun",
            "run_dir": run_dir,
        },
    }
    if not success:
        if error_code:
            payload["errorCode"] = str(error_code)
        if error_message:
            payload["errorMessage"] = str(error_message)[:4000]
    return payload


def maybe_send_autoexp_callback(
    *,
    db: Session,
    task: Task,
    task_run: Optional[TaskRun],
    mode: Optional[str] = None,
    run_dir: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> bool:
    url = (settings.AUTOEXP_CALLBACK_URL or "").strip()
    if not url:
        return False
    if not _is_external_task(db, task):
        return False

    headers = {"Content-Type": "application/json"}
    token = (settings.AUTOEXP_CALLBACK_TOKEN or "").strip()
    if token:
        headers["X-Callback-Token"] = token

    payload = _build_payload(
        task=task,
        task_run=task_run,
        mode=mode,
        run_dir=run_dir,
        error_code=error_code,
        error_message=error_message,
    )
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    max_retries = max(0, int(getattr(settings, "AUTOEXP_CALLBACK_MAX_RETRIES", 0) or 0))
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = _http.request("POST", url, body=body, headers=headers)
            status = int(getattr(resp, "status", 0) or 0)
            if 200 <= status < 300:
                logger.info("auto-exp callback ok task_id=%s status=%s http=%s", task.id, task.status, status)
                return True
            logger.warning("auto-exp callback non-2xx task_id=%s status=%s http=%s", task.id, task.status, status)
        except Exception as e:
            logger.warning("auto-exp callback error task_id=%s status=%s err=%s", task.id, task.status, str(e))

        if attempts > max_retries:
            return False
        time.sleep(min(1.0 * attempts, 3.0))

