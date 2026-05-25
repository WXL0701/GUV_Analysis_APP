import os
import subprocess
import signal
import uuid
import time
import logging
import traceback
import shutil
import json
import hashlib
from datetime import datetime
from typing import Optional, Any
import threading
import queue
from app.worker.celery_app import celery_app
from app.core.config import settings
from app.services.minio_service import MinioService
from app.services.autoexp_callback_service import send_autoexp_callback_detail
from app.db.session import SessionLocal
from app.db.models import Task, TaskRun, AppConfig, User

logger = logging.getLogger(__name__)

def _append_runtime_log(log_file: str, message: str, level: str = "INFO", module: str = __name__):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    effective_level = (level or "INFO").upper()
    if effective_level == "INFO":
        prefix = (message or "").split(":", 1)[0].strip().upper()
        if prefix in ("WARN", "WARNING"):
            effective_level = "WARN"
        elif prefix in ("ERROR", "FAILED"):
            effective_level = "ERROR"
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {effective_level} {module} {message}\n")
            f.flush()
    except Exception:
        pass

def _get_task_type_label(db, task: Task) -> tuple[str, bool]:
    if task.user_id:
        user = db.query(User).filter(User.id == task.user_id).first()
        if user and user.role == "external":
            return "三方自动化任务", True
    return "手动任务", False

def _append_callback_detail(log_file: str, detail: dict[str, Any]) -> None:
    if detail.get("skipped"):
        msg = f"CALLBACK skipped=1 reason={detail.get('skip_reason')} url={detail.get('url') or '-'}"
        _append_runtime_log(log_file, msg, level="INFO")
        return
    else:
        ok = bool(detail.get("ok"))
        status = detail.get("status")
        attempts = detail.get("attempts")
        url = detail.get("url") or "-"
        duration_ms = detail.get("duration_ms")
        err = detail.get("error")
        msg = f"CALLBACK ok={ok} http={status} attempts={attempts} duration_ms={duration_ms} url={url}"
        if err:
            msg = f"{msg} error={err}"
        _append_runtime_log(log_file, msg, level=("INFO" if ok else "WARN"))
        req = detail.get("request_body")
        if req:
            _append_runtime_log(log_file, f"CALLBACK_REQUEST body={req}", level=("INFO" if ok else "WARN"))
        resp_body = detail.get("response_body")
        if resp_body:
            _append_runtime_log(log_file, f"CALLBACK_RESPONSE body={resp_body}", level=("INFO" if ok else "WARN"))

def _send_callback_and_log(
    *,
    db,
    task: Task,
    task_run: Optional[TaskRun],
    mode: Optional[str],
    run_dir: Optional[str],
    error_code: Optional[str],
    error_message: Optional[str],
    log_file: str,
    is_external: bool,
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
    if is_external:
        _append_callback_detail(log_file, detail)
    return bool(detail.get("ok"))

# Helper to get MinIO service (can't rely on Depends in Celery)
def get_minio_service():
    return MinioService(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        bucket=settings.MINIO_BUCKET,
        presign_expires_sec=settings.MINIO_PRESIGN_EXPIRES_SECONDS,
        connect_timeout_sec=settings.MINIO_HTTP_CONNECT_TIMEOUT_SECONDS,
        read_timeout_sec=settings.MINIO_HTTP_READ_TIMEOUT_SECONDS,
    )

def _read_json(path: str) -> Optional[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_json_atomic(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp.{uuid.uuid4().hex}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def _load_params_cache(task_id: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    cache_path = os.path.join(settings.RUN_BASE_DIR, str(task_id), "params.latest.json")
    sha_path = os.path.join(settings.RUN_BASE_DIR, str(task_id), "params.latest.sha256")
    data = _read_json(cache_path) if os.path.exists(cache_path) else None
    sha = _read_text(sha_path).strip() if os.path.exists(sha_path) and _read_text(sha_path) else None
    return data, sha

def _sync_params_to_run_dir(
    *,
    task_id: str,
    run_id: str,
    minio: MinioService,
    params_key: str,
    run_dir: str,
    log_file: str,
) -> tuple[str, str]:
    params_path = os.path.join(run_dir, "params.json")
    tmp_path = f"{params_path}.tmp.{uuid.uuid4().hex}"
    expected_sha: Optional[str] = None
    try:
        st = minio.client.stat_object(minio.bucket, params_key)
        meta = getattr(st, "metadata", None) or {}
        for k, v in meta.items():
            if str(k).lower().endswith("sha256"):
                expected_sha = str(v).strip()
                break
    except Exception:
        expected_sha = None

    last_err: Optional[str] = None
    for attempt in range(2):
        try:
            _append_runtime_log(log_file, f"Downloading params from {params_key} to {params_path} (attempt {attempt+1})")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            minio.client.fget_object(minio.bucket, params_key, tmp_path)
            if expected_sha:
                actual_sha = _sha256_file(tmp_path)
                if actual_sha.lower() != expected_sha.lower():
                    raise RuntimeError(f"params sha256 mismatch expected={expected_sha} actual={actual_sha}")
            os.replace(tmp_path, params_path)
            return params_path, "minio"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)}"
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            time.sleep(0.2)

    cached_params, cached_sha = _load_params_cache(task_id)
    if cached_params is not None:
        try:
            body = json.dumps(cached_params, indent=2, ensure_ascii=False).encode("utf-8")
            actual_sha = hashlib.sha256(body).hexdigest()
            if cached_sha and actual_sha.lower() != cached_sha.lower():
                _append_runtime_log(log_file, f"WARN: Params cache sha mismatch expected={cached_sha} actual={actual_sha}")
            with open(tmp_path, "wb") as f:
                f.write(body)
            os.replace(tmp_path, params_path)
            _append_runtime_log(log_file, "Using cached params.latest.json")
            return params_path, "cache"
        except Exception as e:
            last_err = f"{last_err}; cache_error={type(e).__name__}: {str(e)}" if last_err else f"{type(e).__name__}: {str(e)}"
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    _append_runtime_log(log_file, f"WARN: Params unavailable, using empty params. error={last_err or 'unknown'}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("{}")
    os.replace(tmp_path, params_path)
    return params_path, "empty"

def _should_cancel(task_id: str, run_id: str, run_dir: str, images_dir: str, db) -> bool:
    try:
        if os.path.exists(os.path.join(run_dir, "cancel")):
            return True
    except Exception:
        pass

    try:
        if os.path.exists(os.path.join(images_dir, "cancel.global")):
            return True
        if run_id and os.path.exists(os.path.join(images_dir, f"cancel.{run_id}")):
            return True
    except Exception:
        pass

    try:
        try:
            if hasattr(db, "expire_all"):
                db.expire_all()
        except Exception:
            pass

        task = (
            db.query(Task)
            .execution_options(populate_existing=True)
            .filter(Task.id == task_id)
            .first()
        )
        if not task:
            return True
        if bool(getattr(task, "cancel_requested", False)):
            return True
    except Exception:
        return True

    try:
        run_uuid = uuid.UUID(run_id)
        run = (
            db.query(TaskRun)
            .execution_options(populate_existing=True)
            .filter(TaskRun.id == run_uuid, TaskRun.task_id == task_id)
            .first()
        )
        if not run:
            return True
        if run.status == "CANCELED":
            return True
    except Exception:
        return True

    return False

def _update_transfer_status(
    status_path: str,
    base: dict[str, Any],
    *,
    bytes_total: Optional[int] = None,
    bytes_done: Optional[int] = None,
    state: Optional[str] = None,
    message: Optional[str] = None,
    etag: Optional[str] = None,
) -> dict[str, Any]:
    now = time.time()
    status = dict(base)
    status["updated_at"] = now
    if state is not None:
        status["state"] = state
    if message is not None:
        status["message"] = message
    if etag is not None:
        status["etag"] = etag

    if bytes_total is not None:
        status["bytes_total"] = int(bytes_total)
    if bytes_done is not None:
        status["bytes_done"] = int(bytes_done)

    total = status.get("bytes_total") or 0
    done = status.get("bytes_done") or 0
    started_at = status.get("started_at") or now
    status["started_at"] = started_at

    percent = 0.0
    if total > 0:
        percent = max(0.0, min(100.0, (float(done) / float(total)) * 100.0))
    status["percent"] = round(percent, 2)

    elapsed = max(0.001, now - float(started_at))
    speed_bps = float(done) / elapsed if done > 0 else 0.0
    status["speed_bps"] = round(speed_bps, 2)

    if total > 0 and speed_bps > 1e-6 and done <= total:
        status["eta_seconds"] = int(max(0.0, (float(total - done) / speed_bps)))
    else:
        status["eta_seconds"] = None

    _write_json_atomic(status_path, status)
    return status

def _download_nd2_with_progress(
    *,
    task_id: str,
    run_id: str,
    minio: MinioService,
    key: str,
    cached_nd2_path: str,
    images_dir: str,
    run_dir: str,
    db,
    log_file: str,
) -> None:
    status_path = os.path.join(run_dir, "transfer_nd2.json")
    meta_path = os.path.join(images_dir, "nd2.meta.json")
    part_path = f"{cached_nd2_path}.part"

    stat = None
    stat_error_msg = None
    try:
        stat = minio.client.stat_object(minio.bucket, key)
    except Exception as e:
        stat_error_msg = str(e)
        _append_runtime_log(log_file, f"WARN: Failed to stat ND2 before transfer: {type(e).__name__}: {str(e)}")

    remote_size = int(getattr(stat, "size", 0) or 0) if stat else 0
    remote_etag = getattr(stat, "etag", None) if stat else None
    remote_last_modified = getattr(stat, "last_modified", None) if stat else None

    local_exists = os.path.exists(cached_nd2_path)
    local_size = 0
    if local_exists:
        try:
            local_size = os.path.getsize(cached_nd2_path)
        except Exception:
            local_size = 0

    meta = _read_json(meta_path) or {}
    meta_etag = meta.get("etag")
    meta_total = meta.get("bytes_total")

    marker_path = os.path.join(images_dir, "nd2.remote_deleted.json")
    if os.path.exists(marker_path) and local_exists and local_size > 0:
        base = {"task_id": task_id, "run_id": run_id, "state": "ready", "started_at": time.time()}
        total = meta_total or local_size
        _update_transfer_status(status_path, base, bytes_total=total, bytes_done=total, state="ready", message="Using cached ND2 (remote deleted)", etag=meta_etag)
        return

    if stat_error_msg and local_exists and local_size > 0:
        msg = stat_error_msg.lower()
        if any(x in msg for x in ("nosuchkey", "notfound", "404")):
            base = {"task_id": task_id, "run_id": run_id, "state": "ready", "started_at": time.time()}
            total = meta_total or local_size
            _update_transfer_status(status_path, base, bytes_total=total, bytes_done=total, state="ready", message="Using cached ND2 (remote missing)", etag=meta_etag)
            return

    if local_exists and remote_etag and meta_etag == remote_etag:
        base = {"task_id": task_id, "run_id": run_id, "state": "ready", "started_at": time.time()}
        _update_transfer_status(status_path, base, bytes_total=remote_size or meta_total or local_size, bytes_done=remote_size or meta_total or local_size, state="ready", message="Using cached ND2", etag=remote_etag)
        return

    if local_exists and remote_size > 0 and local_size == remote_size and (meta_total in (None, remote_size)):
        base = {"task_id": task_id, "run_id": run_id, "state": "ready", "started_at": time.time()}
        _update_transfer_status(status_path, base, bytes_total=remote_size, bytes_done=remote_size, state="ready", message="Using cached ND2 (size matched)", etag=remote_etag)
        meta_out: dict[str, Any] = {
            "etag": remote_etag,
            "bytes_total": remote_size,
            "remote_key": key,
            "updated_at": time.time(),
        }
        if remote_last_modified is not None:
            try:
                meta_out["last_modified"] = remote_last_modified.isoformat()
            except Exception:
                pass
        _write_json_atomic(meta_path, meta_out)
        return

    # Check disk space since download is required
    try:
        total, used, free = shutil.disk_usage(os.path.dirname(images_dir) or settings.RUN_BASE_DIR)
        required_free = int(remote_size * 1.1) if remote_size else 1024 * 1024 * 100  # 1.1x safety or 100MB
        if free < required_free:
             raise RuntimeError(f"Insufficient disk space. free={free} required~={required_free}")
    except Exception as e:
        if "Insufficient disk space" in str(e):
             raise
        # Ignore other errors (e.g. path not found yet)
        pass

    if _should_cancel(task_id, run_id, run_dir, images_dir, db):
        base = {"task_id": task_id, "run_id": run_id, "state": "canceled", "started_at": time.time()}
        _update_transfer_status(status_path, base, bytes_total=remote_size, bytes_done=0, state="canceled", message="Canceled before start", etag=remote_etag)
        raise RuntimeError("Transfer canceled")

    try:
        if os.path.exists(part_path) and os.path.isfile(part_path):
            os.remove(part_path)
    except Exception:
        pass

    base = {"task_id": task_id, "run_id": run_id, "state": "transferring", "started_at": time.time()}
    _update_transfer_status(status_path, base, bytes_total=remote_size, bytes_done=0, state="transferring", message="Starting transfer", etag=remote_etag)
    _append_runtime_log(log_file, "ND2 transfer started")

    response = None
    bytes_done = 0
    last_write = 0.0
    try:
        response = minio.client.get_object(minio.bucket, key)
        with open(part_path, "wb") as out:
            for chunk in response.stream(8 * 1024 * 1024):
                if not chunk:
                    continue
                if _should_cancel(task_id, run_id, run_dir, images_dir, db):
                    raise RuntimeError("Transfer canceled")
                out.write(chunk)
                bytes_done += len(chunk)
                now = time.time()
                if now - last_write >= 0.5:
                    _update_transfer_status(status_path, base, bytes_total=remote_size, bytes_done=bytes_done, state="transferring", message="Transferring", etag=remote_etag)
                    last_write = now

        os.replace(part_path, cached_nd2_path)
        _update_transfer_status(status_path, base, bytes_total=remote_size or bytes_done, bytes_done=remote_size or bytes_done, state="ready", message="Transfer complete", etag=remote_etag)
        meta_out: dict[str, Any] = {
            "etag": remote_etag,
            "bytes_total": remote_size or bytes_done,
            "remote_key": key,
            "updated_at": time.time(),
        }
        if remote_last_modified is not None:
            try:
                meta_out["last_modified"] = remote_last_modified.isoformat()
            except Exception:
                pass
        _write_json_atomic(meta_path, meta_out)
        _append_runtime_log(log_file, "ND2 transfer ready")
    except Exception as e:
        try:
            if os.path.exists(part_path) and os.path.isfile(part_path):
                os.remove(part_path)
        except Exception:
            pass

        state = "canceled" if "canceled" in str(e).lower() else "failed"
        try:
            _update_transfer_status(status_path, base, bytes_total=remote_size, bytes_done=bytes_done, state=state, message=str(e)[:500], etag=remote_etag)
        except Exception:
            pass
        raise
    finally:
        try:
            if response is not None:
                response.close()
                response.release_conn()
        except Exception:
            pass

def _maybe_cleanup_remote_nd2_after_success(
    *,
    task_id: str,
    minio: MinioService,
    nd2_key: str,
    cached_nd2_path: str,
    images_dir: str,
    log_file: str,
) -> None:
    try:
        marker_path = os.path.join(images_dir, "nd2.remote_deleted.json")
        if os.path.exists(marker_path):
            return

        nd2_key = str(nd2_key or "")
        if not nd2_key:
            return

        safe_prefix = f"tasks/{task_id}/"
        if not nd2_key.startswith(safe_prefix):
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup due to unexpected key={nd2_key}")
            return

        if not os.path.exists(cached_nd2_path):
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because local file missing: {cached_nd2_path}")
            return

        try:
            local_size = int(os.path.getsize(cached_nd2_path) or 0)
        except Exception:
            local_size = 0
        if local_size <= 0:
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because local file size invalid: {local_size}")
            return

        try:
            with open(cached_nd2_path, "rb") as f:
                head = f.read(64)
            if not head:
                _append_runtime_log(log_file, "WARN: Skip remote ND2 cleanup because local file unreadable/empty")
                return
        except Exception as e:
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because local file unreadable: {type(e).__name__}: {str(e)}")
            return

        meta_path = os.path.join(images_dir, "nd2.meta.json")
        meta = _read_json(meta_path) or {}
        meta_remote_key = meta.get("remote_key")
        if meta_remote_key and str(meta_remote_key) != nd2_key:
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because meta remote_key mismatch: {meta_remote_key} != {nd2_key}")
            return
        meta_etag = meta.get("etag")
        meta_total = meta.get("bytes_total")

        remote_size: Optional[int] = None
        remote_etag: Optional[str] = None
        try:
            st = minio.client.stat_object(minio.bucket, nd2_key)
            remote_size = int(getattr(st, "size", 0) or 0)
            remote_etag = getattr(st, "etag", None)
        except Exception as e:
            msg = str(e).lower()
            if any(x in msg for x in ("nosuchkey", "notfound", "404")):
                _append_runtime_log(log_file, f"Remote ND2 already missing, skip cleanup. key={nd2_key}")
                return
            remote_size = None
            remote_etag = None
            _append_runtime_log(log_file, f"WARN: Failed to stat remote ND2 before cleanup: {type(e).__name__}: {str(e)}")

        if remote_size is not None and remote_size > 0 and local_size != remote_size:
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because size mismatch local={local_size} remote={remote_size}")
            return
        if remote_size in (None, 0) and meta_total and int(meta_total) > 0 and local_size != int(meta_total):
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because size mismatch local={local_size} meta_total={meta_total}")
            return
        if remote_etag and meta_etag and str(remote_etag) != str(meta_etag):
            _append_runtime_log(log_file, f"WARN: Skip remote ND2 cleanup because etag mismatch meta={meta_etag} remote={remote_etag}")
            return

        try:
            minio.client.remove_object(minio.bucket, nd2_key)
        except Exception as e:
            msg = str(e).lower()
            if any(x in msg for x in ("nosuchkey", "notfound", "404")):
                _append_runtime_log(log_file, f"Remote ND2 already missing, skip cleanup. key={nd2_key}")
                return
            _append_runtime_log(log_file, f"WARN: Remote ND2 cleanup failed: {type(e).__name__}: {str(e)}")
            return

        _write_json_atomic(
            marker_path,
            {
                "deleted_at": time.time(),
                "remote_key": nd2_key,
                "bytes_local": local_size,
                "etag": remote_etag or meta_etag,
            },
        )
        _append_runtime_log(log_file, f"Remote ND2 deleted. key={nd2_key} bytes_local={local_size}")
    except Exception as e:
        _append_runtime_log(log_file, f"WARN: Remote ND2 cleanup skipped due to error: {type(e).__name__}: {str(e)}")

@celery_app.task(bind=True)
def run_analysis_task(self, task_id: str, mode: str, run_id: str = None):
    """
    Celery task to run the MATLAB analysis pipeline.
    mode: 'debug' or 'final'
    run_id: Optional UUID string for the specific run instance
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"status": "failed", "error": "Task not found"}

        log_file = os.path.join(settings.RUN_BASE_DIR, str(task_id), str(run_id or "unknown"), "runtime.log")
        _append_runtime_log(log_file, f"Worker received task. mode={mode} task_id={task_id} run_id={run_id}")

        # Handle Run ID
        if not run_id:
            run_id = str(uuid.uuid4())
            # Create TaskRun if not exists (fallback)
            run_uuid = uuid.UUID(run_id)
            task_run = TaskRun(
                id=run_uuid,
                task_id=task_id,
                run_mode=mode,
                status="QUEUED"
            )
            db.add(task_run)
        else:
            run_uuid = uuid.UUID(run_id)
            task_run = db.query(TaskRun).filter(TaskRun.id == run_uuid, TaskRun.task_id == task_id).first()
            if task_run:
                pass
            else:
                 # Should have been created by API, but create if missing
                task_run = TaskRun(
                    id=run_uuid,
                    task_id=task_id,
                    run_mode=mode,
                    status="QUEUED"
                )
                db.add(task_run)

        task.run_id_current = run_id
        db.commit()

        log_file = os.path.join(settings.RUN_BASE_DIR, str(task_id), str(run_id), "runtime.log")
        _append_runtime_log(log_file, f"Worker started. mode={mode}")
        task_type_label, is_external = _get_task_type_label(db, task)
        _append_runtime_log(log_file, f"TASK_INIT task_id={task_id} run_id={run_id} type={task_type_label}")
        
        # Update started_at
        if task_run:
            task_run.started_at = datetime.utcnow()
            task_run.status = "RUNNING"
            db.commit()

        # Prepare Directory Structure
        # 1. Images Directory (Shared)
        images_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), "images")
        os.makedirs(images_dir, exist_ok=True)
        # Use original filename to prevent confusion, ensure .nd2 extension
        original_filename = os.path.basename(task.nd2_object_key)
        if not original_filename.lower().endswith('.nd2'):
             original_filename += ".nd2"
        cached_nd2_path = os.path.join(images_dir, original_filename)

        # 2. Run Directory (Specific)
        run_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), str(run_id))
        os.makedirs(run_dir, exist_ok=True)
        
        # Ensure output directories exist if script needs them
        # Script likely writes to base_path/output...
        os.makedirs(os.path.join(run_dir, "output", "debug"), exist_ok=True)
        os.makedirs(os.path.join(run_dir, "output", "final"), exist_ok=True)
        os.makedirs(os.path.join(run_dir, "logs"), exist_ok=True)

        minio = get_minio_service()
        
        # Download inputs
        try:
            _append_runtime_log(log_file, f"Preparing inputs. nd2_key={task.nd2_object_key}")
            nd2_size = None
            try:
                stat = minio.client.stat_object(minio.bucket, task.nd2_object_key)
                nd2_size = getattr(stat, "size", None)
            except Exception:
                logger.exception("Failed to stat ND2 object before download task_id=%s key=%s", task_id, task.nd2_object_key)
                _append_runtime_log(log_file, "WARN: Failed to stat ND2 object before download")

            # Check logic moved to _download_nd2_with_progress to account for caching
            # if nd2_size is not None and free is not None:
            #     required_free = int(nd2_size * 1.2)
            #     if free < required_free:
            #         raise RuntimeError(f"Insufficient disk space. free={free} required~={required_free}")
            _download_nd2_with_progress(
                task_id=str(task_id),
                run_id=str(run_id),
                minio=minio,
                key=str(task.nd2_object_key),
                cached_nd2_path=cached_nd2_path,
                images_dir=images_dir,
                run_dir=run_dir,
                db=db,
                log_file=log_file,
            )
            
            # Download params.json to run_dir
            params_key = task.params_object_key_current
            if not params_key:
                # Fallback: tasks/{task_id}/params.json
                params_key = f"tasks/{task_id}/params.json"
            params_path, params_source = _sync_params_to_run_dir(
                task_id=str(task_id),
                run_id=str(run_id),
                minio=minio,
                params_key=str(params_key),
                run_dir=run_dir,
                log_file=log_file,
            )

            try:
                with open(params_path, "r", encoding="utf-8") as f:
                    params_data = json.load(f)
                if task_run:
                    task_run.params_snapshot = params_data
                    db.commit()
            except Exception:
                logger.exception(
                    "Failed to save params snapshot task_id=%s run_id=%s source=%s",
                    task_id,
                    run_id,
                    params_source,
                )

        except Exception as e:
            logger.exception("Download inputs failed task_id=%s run_id=%s", task_id, run_id)
            _append_runtime_log(log_file, f"ERROR: Download inputs failed: {str(e)}")
            canceled = "canceled" in str(e).lower() or _should_cancel(str(task_id), str(run_id), run_dir, images_dir, db)
            if canceled:
                task.status = "CANCELED"
                task.last_error = None
                if task_run:
                    task_run.status = "CANCELED"
                db.commit()
                _send_callback_and_log(
                    db=db,
                    task=task,
                    task_run=task_run,
                    mode=mode,
                    run_dir=run_dir,
                    error_code="GUV_RUN_CANCELED",
                    error_message=None,
                    log_file=log_file,
                    is_external=is_external,
                )
                return {"status": "canceled"}
            else:
                task.status = "FAILED"
                task.last_error = (f"Download failed: {str(e)}\n" + traceback.format_exc())[:4000]
                if task_run:
                    task_run.status = "FAILED"
                db.commit()
                _send_callback_and_log(
                    db=db,
                    task=task,
                    task_run=task_run,
                    mode=mode,
                    run_dir=run_dir,
                    error_code="GUV_RUN_FAILED",
                    error_message=task.last_error,
                    log_file=log_file,
                    is_external=is_external,
                )
                return {"status": "failed", "error": str(e)}

        # Run Script
        # Detect OS to choose script
        
        # Resolve PIPELINE_ROOT
        pipeline_root = settings.PIPELINE_ROOT
        try:
             # db is already open
             config_root = db.query(AppConfig).filter(AppConfig.key == "system.pipeline_root").first()
             if config_root and config_root.value:
                 pipeline_root = config_root.value
                 _append_runtime_log(log_file, f"Configuration loaded: system.pipeline_root={pipeline_root}")
             else:
                 _append_runtime_log(log_file, f"Configuration using default settings: PIPELINE_ROOT={pipeline_root}")
        except Exception as e:
             _append_runtime_log(log_file, f"Error loading configuration: {str(e)}")
             pass

        matlab_bin = "matlab"
        try:
             config_ver = db.query(AppConfig).filter(AppConfig.key == "system.matlab_version").first()
             if config_ver and config_ver.value:
                 if config_ver.value == "R2018a":
                     matlab_bin = "/usr/local/MATLAB/R2018a/bin/matlab"
                 elif config_ver.value == "R2024a":
                     matlab_bin = "/usr/local/MATLAB/R2024a/bin/matlab"
                 _append_runtime_log(log_file, f"Configuration loaded: system.matlab_version={config_ver.value} -> BIN={matlab_bin}")
        except Exception as e:
             _append_runtime_log(log_file, f"Error loading matlab version: {str(e)}")

        env = os.environ.copy()
        env["MATLAB_BIN"] = matlab_bin
        if pipeline_root:
            env["PIPELINE_ROOT"] = pipeline_root
            _append_runtime_log(log_file, f"Environment set: PIPELINE_ROOT={pipeline_root}")
        else:
            _append_runtime_log(log_file, "WARNING: PIPELINE_ROOT not set in environment")

        if os.name == 'nt':
            script_path = os.path.join(os.getcwd(), "scripts", "run_matlab_task.bat")
            cmd = [script_path, str(task_id), str(run_id), mode, 
                   cached_nd2_path, 
                   params_path, 
                   run_dir]
        else:
            script_path = os.path.join(os.getcwd(), "scripts", "run_matlab_task.sh")
            cmd = ["bash", script_path, str(task_id), str(run_id), mode, 
                   cached_nd2_path, 
                   params_path, 
                   run_dir]
        
        if not os.path.exists(script_path):
            msg = f"ERROR: Script not found: {script_path}"
            _append_runtime_log(log_file, msg)
            task.status = "FAILED"
            task.last_error = msg
            if task_run:
                task_run.status = "FAILED"
            db.commit()
            _send_callback_and_log(
                db=db,
                task=task,
                task_run=task_run,
                mode=mode,
                run_dir=run_dir,
                error_code="GUV_RUN_FAILED",
                error_message=msg,
                log_file=log_file,
                is_external=is_external,
            )
            return {"status": "failed", "error": msg}
        
        try:
            if task_run:
                task_run.status = "RUNNING"
            if mode == 'debug':
                task.status = "RUNNING_DEBUG"
            else:
                task.status = "RUNNING_FINAL"
            db.commit()

            _append_runtime_log(log_file, "RUNNING")
            _append_runtime_log(log_file, f"Starting process: {' '.join(cmd[:4])} ...")
            with open(log_file, "a", buffering=1, encoding="utf-8") as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                    start_new_session=os.name != "nt",
                )
                line_q: "queue.Queue[Optional[str]]" = queue.Queue()

                def _reader():
                    try:
                        assert process.stdout is not None
                        for line in process.stdout:
                            line_q.put(line)
                    except Exception:
                        pass
                    finally:
                        line_q.put(None)

                t = threading.Thread(target=_reader, daemon=True)
                t.start()

                canceled = False
                while True:
                    if _should_cancel(str(task_id), str(run_id), run_dir, images_dir, db):
                        canceled = True
                        _append_runtime_log(log_file, "CANCEL requested, terminating process")
                        try:
                            if os.name != "nt":
                                os.killpg(process.pid, signal.SIGTERM)
                            else:
                                process.terminate()
                        except Exception:
                            pass
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            try:
                                if os.name != "nt":
                                    os.killpg(process.pid, signal.SIGKILL)
                                else:
                                    process.kill()
                            except Exception:
                                pass
                        break

                    try:
                        line = line_q.get(timeout=0.25)
                    except queue.Empty:
                        if process.poll() is not None:
                            break
                        continue

                    if line is None:
                        break
                    f.write(line)
                    f.flush()

                    # Parse progress
                    try:
                        lower_line = line.lower()
                        if "progress:" in lower_line:
                            import re
                            match = re.search(r"progress:\s*(\d+)", lower_line)
                            if match:
                                p = int(match.group(1))
                                if 0 <= p <= 100 and task.progress != p:
                                    task.progress = p
                                    db.commit()
                    except Exception:
                        pass

                if canceled:
                    task.status = "CANCELED"
                    task.last_error = None
                    if task_run:
                        task_run.status = "CANCELED"
                    _append_runtime_log(log_file, "CANCELED")
                    db.commit()
                    _send_callback_and_log(
                        db=db,
                        task=task,
                        task_run=task_run,
                        mode=mode,
                        run_dir=run_dir,
                        error_code="GUV_RUN_CANCELED",
                        error_message=None,
                        log_file=log_file,
                        is_external=is_external,
                    )
                    return {"status": "canceled"}

                process.wait()
                if process.returncode != 0:
                    raise Exception(f"Process exited with code {process.returncode}")
                
            task.status = "SUCCEEDED"
            if task_run:
                task_run.status = "SUCCEEDED"
            _append_runtime_log(log_file, "SUCCEEDED")
            _maybe_cleanup_remote_nd2_after_success(
                task_id=str(task_id),
                minio=minio,
                nd2_key=str(task.nd2_object_key),
                cached_nd2_path=cached_nd2_path,
                images_dir=images_dir,
                log_file=log_file,
            )
        except Exception as e:
            task.status = "FAILED"
            task.last_error = str(e)[:4000]
            if task_run:
                task_run.status = "FAILED"
            logger.exception("Pipeline execution failed task_id=%s run_id=%s", task_id, run_id)
            _append_runtime_log(log_file, f"FAILED: {str(e)}")
            
        db.commit()
        if task.status == "FAILED":
            _send_callback_and_log(
                db=db,
                task=task,
                task_run=task_run,
                mode=mode,
                run_dir=run_dir,
                error_code="GUV_RUN_FAILED",
                error_message=task.last_error,
                log_file=log_file,
                is_external=is_external,
            )
        elif task.status == "SUCCEEDED":
            _send_callback_and_log(
                db=db,
                task=task,
                task_run=task_run,
                mode=mode,
                run_dir=run_dir,
                error_code=None,
                error_message=None,
                log_file=log_file,
                is_external=is_external,
            )
        return {"status": task.status}
        
    finally:
        db.close()
