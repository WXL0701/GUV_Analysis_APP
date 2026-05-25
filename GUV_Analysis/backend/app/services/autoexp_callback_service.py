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


def send_autoexp_callback_detail(
    *,
    db: Session,
    task: Task,
    task_run: Optional[TaskRun],
    mode: Optional[str] = None,
    run_dir: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    url = (settings.AUTOEXP_CALLBACK_URL or "").strip()
    result: Dict[str, Any] = {
        "ok": False,
        "attempts": 0,
        "status": None,
        "error": None,
        "url": url,
        "duration_ms": None,
        "request_body": None,
        "response_body": None,
        "skipped": False,
        "skip_reason": None,
    }
    if not url:
        result["skipped"] = True
        result["skip_reason"] = "no_url"
        return result
    if not _is_external_task(db, task):
        result["skipped"] = True
        result["skip_reason"] = "not_external"
        return result

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
    request_body_full = json.dumps(payload, ensure_ascii=False)
    request_body_preview = request_body_full
    if len(request_body_preview) > 8000:
        request_body_preview = request_body_preview[:8000] + "...(truncated)"
    result["request_body"] = request_body_preview
    body = request_body_full.encode("utf-8")

    max_retries = max(0, int(getattr(settings, "AUTOEXP_CALLBACK_MAX_RETRIES", 0) or 0))
    attempts = 0
    while True:
        attempts += 1
        result["attempts"] = attempts
        try:
            started = time.perf_counter()
            resp = _http.request("POST", url, body=body, headers=headers)
            result["duration_ms"] = int((time.perf_counter() - started) * 1000)
            status = int(getattr(resp, "status", 0) or 0)
            result["status"] = status
            try:
                data = getattr(resp, "data", None)
                if isinstance(data, (bytes, bytearray)):
                    text = data.decode("utf-8", errors="replace")
                elif data is None:
                    text = ""
                else:
                    text = str(data)
                if len(text) > 2000:
                    text = text[:2000] + "...(truncated)"
                result["response_body"] = text
            except Exception:
                result["response_body"] = None
            if 200 <= status < 300:
                logger.info("auto-exp callback ok task_id=%s status=%s http=%s", task.id, task.status, status)
                result["ok"] = True
                return result
            logger.warning("auto-exp callback non-2xx task_id=%s status=%s http=%s", task.id, task.status, status)
            result["error"] = f"non-2xx:{status}"
        except Exception as e:
            logger.warning("auto-exp callback error task_id=%s status=%s err=%s", task.id, task.status, str(e))
            result["error"] = f"{type(e).__name__}: {str(e)}"

        if attempts > max_retries:
            return result
        time.sleep(min(1.0 * attempts, 3.0))


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
    detail = send_autoexp_callback_detail(
        db=db,
        task=task,
        task_run=task_run,
        mode=mode,
        run_dir=run_dir,
        error_code=error_code,
        error_message=error_message,
    )
    return bool(detail.get("ok"))
