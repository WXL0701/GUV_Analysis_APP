from typing import Any, List, Optional, Dict
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc
import logging
import json
from datetime import datetime, timedelta
import hashlib
import time

from app.api import deps
from app.core.config import settings
from app.db.models import Task, User, TaskArtifact, TaskRun, TaskEvent
from app.schemas import TaskCreate, TaskCreateResponse, TaskOut, TaskPage, TaskQueueUpdate, TaskRunOut, TaskAutoRunRequest, TaskAutoRunResponse
from app.services.queue_service import QueueService
import os
import uuid
import shutil
import redis


router = APIRouter()
logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None

def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            decode_responses=True,
        )
    return _redis_client

def _upload_meta_key(task_id: str) -> str:
    return f"upload:{task_id}:meta"

def _upload_parts_key(task_id: str) -> str:
    return f"upload:{task_id}:parts"

def _set_upload_meta(task_id: str, mapping: dict[str, Any]) -> None:
    r = _get_redis()
    key = _upload_meta_key(task_id)
    flat = {k: str(v) for k, v in mapping.items() if v is not None}
    if flat:
        r.hset(key, mapping=flat)
        r.expire(key, 7 * 24 * 3600)

def _get_upload_meta(task_id: str) -> dict[str, str]:
    r = _get_redis()
    return r.hgetall(_upload_meta_key(task_id)) or {}

def _set_upload_paused(task_id: str, paused: bool) -> None:
    _set_upload_meta(task_id, {"paused": 1 if paused else 0, "updated_at": int(time.time())})

def _is_upload_paused(task_id: str) -> bool:
    meta = _get_upload_meta(task_id)
    return (meta.get("paused") or "0") == "1"

def _cleanup_upload_state(task_id: str) -> None:
    r = _get_redis()
    r.delete(_upload_meta_key(task_id))
    r.delete(_upload_parts_key(task_id))

def _s3_endpoint_url() -> str:
    ep = str(settings.MINIO_ENDPOINT or "")
    if ep.startswith("http://") or ep.startswith("https://"):
        return ep
    scheme = "https" if settings.MINIO_SECURE else "http"
    return f"{scheme}://{ep}"

def _create_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=_s3_endpoint_url(),
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

def _read_local_params_cache(task_id: str) -> Optional[dict[str, Any]]:
    cache_path = os.path.join(settings.RUN_BASE_DIR, str(task_id), "params.latest.json")
    try:
        if not os.path.exists(cache_path):
            return None
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _resolve_run_dir(
    *,
    task_id: str,
    run_id: Optional[str],
    db: Session,
    current_user: User,
) -> tuple[Task, str, str]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    effective_run_id: Optional[str] = run_id
    if not effective_run_id:
        if task.run_id_current:
            effective_run_id = str(task.run_id_current)
        else:
            latest = (
                db.query(TaskRun)
                .filter(TaskRun.task_id == task_id)
                .order_by(TaskRun.created_at.desc())
                .first()
            )
            if latest:
                effective_run_id = str(latest.id)

    if not effective_run_id:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), str(effective_run_id))
    if not os.path.isdir(run_dir):
        raise HTTPException(status_code=404, detail="Run directory not found")

    return task, effective_run_id, run_dir

def _safe_join(base_dir: str, rel_path: str) -> str:
    base_abs = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_abs, rel_path))
    if candidate == base_abs or not candidate.startswith(base_abs + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    return candidate

def _get_task_or_404(*, task_id: str, db: Session, current_user: User) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return task

def _maybe_update_task_progress(db: Session, task: Task, task_id: str, progress: int) -> None:
    now = int(time.time())
    meta = _get_upload_meta(task_id)
    last = int(meta.get("last_db_update_at") or 0)
    if now - last < 2 and progress < 100:
        return
    task.progress = int(progress)
    if task.status == "DRAFT":
        task.status = "UPLOADING"
    db.add(task)
    db.commit()
    _set_upload_meta(task_id, {"last_db_update_at": now})

@router.get("/{task_id}/upload/status")
def get_upload_status(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _ = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    r = _get_redis()
    meta = _get_upload_meta(task_id)
    parts_count = r.scard(_upload_parts_key(task_id))
    file_size = int(meta.get("file_size") or 0)
    uploaded_bytes = int(meta.get("uploaded_bytes") or 0)
    progress = int(meta.get("progress") or 0)
    if file_size > 0:
        progress = max(progress, min(99, int((uploaded_bytes / file_size) * 100)))
    return {
        "task_id": task_id,
        "upload_id": meta.get("upload_id") or "",
        "status": meta.get("status") or "",
        "paused": (meta.get("paused") or "0") == "1",
        "file_size": file_size,
        "chunk_size": int(meta.get("chunk_size") or 0),
        "total_parts": int(meta.get("total_parts") or 0),
        "uploaded_parts_count": int(parts_count or 0),
        "uploaded_bytes": uploaded_bytes,
        "progress": progress,
        "updated_at": int(meta.get("updated_at") or 0),
    }

@router.post("/{task_id}/upload/pause")
def pause_upload(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _ = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    _set_upload_paused(task_id, True)
    return {"status": "ok"}

@router.post("/{task_id}/upload/resume")
def resume_upload(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _ = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    _set_upload_paused(task_id, False)
    return {"status": "ok"}

def _is_task_active_status(status: Optional[str]) -> bool:
    if not status:
        return False
    status_upper = str(status).upper()
    return status_upper == "QUEUED" or status_upper.startswith("RUNNING")

def _safe_rmtree(*, base_dir: str, target_path: str) -> bool:
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    if target_abs == base_abs or not target_abs.startswith(base_abs + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    existed = os.path.exists(target_abs)
    shutil.rmtree(target_abs, ignore_errors=True)
    return existed

def _delete_s3_prefix(*, prefix: str) -> int:
    s3 = _create_s3_client()
    bucket = settings.MINIO_BUCKET

    deleted = 0
    continuation_token: Optional[str] = None

    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)

        contents = resp.get("Contents") or []
        if contents:
            objects = [{"Key": o["Key"]} for o in contents if o.get("Key")]
            for i in range(0, len(objects), 1000):
                chunk = objects[i : i + 1000]
                if not chunk:
                    continue
                del_resp = s3.delete_objects(Bucket=bucket, Delete={"Objects": chunk, "Quiet": True})
                deleted += len(del_resp.get("Deleted") or chunk)

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
            if not continuation_token:
                break
        else:
            break

    return deleted

# --- Demo Params Endpoints ---

def _get_demo_dir() -> str:
    # Based on PIPELINE_ROOT: /app/matlab_packages/GUV_Image_Processor_V1.1.2
    # We want: /app/matlab_packages/Parameters_demo
    pipeline_root = settings.PIPELINE_ROOT
    # If pipeline_root is relative or has trailing slash, handle carefully
    # Assuming standard docker path structure
    matlab_packages_dir = os.path.dirname(pipeline_root.rstrip(os.sep))
    return os.path.join(matlab_packages_dir, "Parameters_demo")

@router.get("/params/demos")
def list_params_demos(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    List available parameter demo files from Parameters_demo directory.
    """
    demo_dir = _get_demo_dir()
    if not os.path.exists(demo_dir):
        # Fallback or empty if not mounted/exists
        return []

    demos = []
    try:
        for filename in os.listdir(demo_dir):
            if filename.endswith(".json"):
                # Use filename as ID (safe enough if we validate later)
                # Create a readable label from filename
                # e.g. "NormalDeformation_Accumulation_Params.json" -> "Normal Deformation Accumulation"
                label = filename.replace("_Params.json", "").replace(".json", "").replace("_", " ")
                demos.append({
                    "id": filename,
                    "name": label,
                    "filename": filename
                })
        # Sort by name
        demos.sort(key=lambda x: x["name"])
    except Exception as e:
        logger.error(f"Failed to list demos: {e}")
        return []
        
    return demos

@router.get("/params/demos/{demo_id}")
def get_params_demo(
    demo_id: str,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get content of a specific parameter demo file.
    """
    # Security check: demo_id must be a simple filename, no path separators
    if os.sep in demo_id or ".." in demo_id:
        raise HTTPException(status_code=400, detail="Invalid demo ID")
        
    if not demo_id.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    demo_dir = _get_demo_dir()
    file_path = os.path.join(demo_dir, demo_id)
    
    # Final check
    if not os.path.abspath(file_path).startswith(os.path.abspath(demo_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Demo file not found")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read demo file {demo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read demo file")

# --- Standard Task Endpoints ---

@router.get("/", response_model=TaskPage)
def read_tasks(
    skip: int = 0,
    limit: int = 10,
    q: Optional[str] = None,
    filter_type: str = "all",
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve tasks with filtering.
    """
    query = db.query(Task)
    if current_user.role != "admin":
        query = query.filter(Task.user_id == current_user.id)
    
    if q:
        query = query.filter(Task.name.ilike(f"%{q}%"))
        
    if filter_type == "active":
        # Active: Queued or Running
        query = query.filter(or_(
            Task.status == "QUEUED",
            Task.status.like("RUNNING%")
        ))
    elif filter_type == "history":
        # History: Succeeded or Failed or Canceled
        query = query.filter(Task.status.in_(["SUCCEEDED", "FAILED", "CANCELED"]))

    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    
    # Populate owner_name for display
    # We convert SQL models to Pydantic models here manually or let FastAPI do it.
    # To add owner_name, we can modify the objects or return dicts.
    # Since we are using ORM mode, we can set the attribute if not transient, 
    # but safest is to attach it.
    
    # However, 'owner' relationship is lazy loaded. 
    # Accessing task.owner.username will trigger a query if not eager loaded.
    # For performance, we could use joinedload, but for now 10 items is fine.
    
    result_items = []
    for t in tasks:
        t_out = TaskOut.from_orm(t)
        if t.owner:
            t_out.owner_name = t.owner.username
        
        if t.status == "QUEUED":
            try:
                pos_info = QueueService.get_queue_position(db, t.id)
                if pos_info["status"] == "QUEUED":
                    t_out.queue_position = pos_info["position"]
            except Exception as e:
                logger.error(f"Error calculating queue position for task {t.id}: {e}")

        result_items.append(t_out)

    return {"items": result_items, "total": total}

@router.get("/stats")
def get_tasks_stats(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get task queue statistics.
    """
    base_query = db.query(Task)
    if current_user.role != "admin":
        base_query = base_query.filter(Task.user_id == current_user.id)
        
    total = base_query.count()
    running = base_query.filter(Task.status.like("RUNNING%")).count()
    queued = base_query.filter(Task.status == "QUEUED").count()
    succeeded = base_query.filter(Task.status == "SUCCEEDED").count()
    failed = base_query.filter(Task.status == "FAILED").count()
    
    # Recent activity (last 7 days)
    recent_activity = []
    today = datetime.utcnow().date()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        start_dt = datetime.combine(d, datetime.min.time())
        end_dt = datetime.combine(d, datetime.max.time())
        
        cnt = base_query.filter(
            Task.created_at >= start_dt,
            Task.created_at <= end_dt
        ).count()
        recent_activity.append({"date": d.strftime("%Y-%m-%d"), "count": cnt})
        
    return {
        "total": total,
        "running": running,
        "queued": queued,
        "succeeded": succeeded,
        "failed": failed,
        "recent_activity": recent_activity
    }

@router.get("/queue/logs", response_model=List[TaskRunOut])
def read_queue_logs(
    limit: int = 50,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get recent task execution logs (TaskRuns).
    """
    query = db.query(TaskRun).join(Task)
    if current_user.role != "admin":
        query = query.filter(Task.user_id == current_user.id)
        
    logs = query.order_by(TaskRun.created_at.desc()).limit(limit).all()
    return logs

@router.put("/{task_id}/queue-info")
def update_task_queue_info(
    task_id: str,
    update: TaskQueueUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update task priority or dependencies.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if update.priority is not None:
        task.priority = update.priority
        
    if update.dependencies is not None:
        task.dependencies = update.dependencies
        
    db.commit()
    return {"status": "ok"}

@router.get("/{task_id}/queue-position")
def get_task_queue_position(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get the position of the task in the queue.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    return QueueService.get_queue_position(db, task_id)

@router.post("/", response_model=TaskCreateResponse)
def create_task(
    *,
    db: Session = Depends(deps.get_db),
    task_in: TaskCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new task.
    """
    existing = db.query(Task).filter(Task.id == task_in.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Task ID already exists")

    # Define object key
    object_key = f"tasks/{task_in.id}/{task_in.filename}"

    task = Task(
        id=task_in.id,
        user_id=current_user.id,
        name=task_in.name,
        nd2_size=task_in.size,
        nd2_object_key=object_key,
        status="DRAFT",
        stage="STAGE_1_UPLOAD"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Generate presigned URL for single PUT (fallback)
    s3 = _create_s3_client()
    
    url = ""
    try:
        url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.MINIO_BUCKET,
                'Key': object_key,
                'ContentType': 'application/octet-stream'
            },
            ExpiresIn=3600
        )
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")

    return {
        "task_id": task.id,
        "uid": str(task.user_id),
        "nd2_object_key": object_key,
        "presigned_put_url": url
    }

@router.post("/auto-run", response_model=TaskAutoRunResponse)
def auto_run_task(
    *,
    db: Session = Depends(deps.get_db),
    payload: TaskAutoRunRequest,
    current_user: User = Depends(deps.get_current_user_for_auto_run),
) -> Any:
    existing = db.query(Task).filter(Task.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Task ID already exists")

    nd2_object_key = f"tasks/{payload.id}/{payload.filename}"
    s3 = _create_s3_client()

    nd2_size: Optional[int] = payload.size
    try:
        head = s3.head_object(Bucket=settings.MINIO_BUCKET, Key=nd2_object_key)
        if nd2_size is None:
            nd2_size = head.get("ContentLength")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        if code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(status_code=400, detail="ND2 object not found in storage")
        raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    task = Task(
        id=payload.id,
        user_id=current_user.id,
        name=payload.name,
        nd2_size=int(nd2_size or 0),
        nd2_object_key=nd2_object_key,
        status="UPLOADED",
        stage="STAGE_2_PARAMS",
        debug_mode=(payload.run_mode == "debug"),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    params_key = f"tasks/{payload.id}/params.json"
    try:
        body = json.dumps(payload.params or {}, indent=2).encode("utf-8")
        sha256 = hashlib.sha256(body).hexdigest()
        s3.put_object(
            Bucket=settings.MINIO_BUCKET,
            Key=params_key,
            Body=body,
            ContentType="application/json",
            Metadata={"sha256": sha256},
        )

        try:
            run_base = settings.RUN_BASE_DIR
            cache_dir = os.path.join(run_base, str(payload.id))
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "params.latest.json")
            cache_sha_path = os.path.join(cache_dir, "params.latest.sha256")
            with open(cache_path, "wb") as f:
                f.write(body)
            with open(cache_sha_path, "w", encoding="utf-8") as f:
                f.write(sha256)
        except Exception:
            logger.exception("Failed to write params cache task_id=%s", payload.id)

        task.params_object_key_current = params_key
        db.commit()
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        run_id = QueueService.submit_task(db, task, payload.run_mode, params_snapshot=(payload.params or {}))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "task_id": task.id,
        "run_id": run_id,
        "nd2_object_key": nd2_object_key,
        "params_key": params_key,
        "status": "queued",
    }

@router.get("/{task_id}", response_model=TaskOut)
def read_task(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get task by ID.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    t_out = TaskOut.from_orm(task)
    if task.status == "QUEUED":
        try:
            pos_info = QueueService.get_queue_position(db, task.id)
            if pos_info["status"] == "QUEUED":
                t_out.queue_position = pos_info["position"]
        except Exception as e:
            logger.error(f"Error calculating queue position for task {task.id}: {e}")
            
    return t_out

@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)

    if _is_task_active_status(task.status):
        raise HTTPException(status_code=409, detail="Task is active, stop it before deleting")

    active_runs = (
        db.query(TaskRun)
        .filter(
            TaskRun.task_id == task_id,
            or_(TaskRun.status == "QUEUED", TaskRun.status.like("RUNNING%")),
        )
        .count()
    )
    if active_runs > 0:
        raise HTTPException(status_code=409, detail="Task has active runs, stop it before deleting")

    prefix = f"tasks/{task_id}/"
    try:
        minio_deleted = _delete_s3_prefix(prefix=prefix)
    except Exception as e:
        logger.exception("Failed to delete MinIO objects prefix=%s", prefix)
        raise HTTPException(status_code=502, detail=f"Failed to delete MinIO objects: {type(e).__name__}: {str(e)}")

    run_base = getattr(settings, "RUN_BASE_DIR", "/data/runs")
    local_root = os.path.join(run_base, str(task_id))
    local_existed = _safe_rmtree(base_dir=run_base, target_path=local_root)
    if local_existed and os.path.exists(local_root):
        raise HTTPException(status_code=500, detail="Failed to delete local run directory")

    artifacts_deleted = (
        db.query(TaskArtifact)
        .filter(TaskArtifact.task_id == task_id)
        .delete(synchronize_session=False)
    )
    events_deleted = (
        db.query(TaskEvent)
        .filter(TaskEvent.task_id == task_id)
        .delete(synchronize_session=False)
    )
    runs_deleted = (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id)
        .delete(synchronize_session=False)
    )
    task_deleted = db.query(Task).filter(Task.id == task_id).delete(synchronize_session=False)
    db.commit()

    return {
        "status": "deleted",
        "task_id": task_id,
        "minio_prefix": prefix,
        "minio_objects_deleted": int(minio_deleted),
        "local_dir_deleted": bool(local_existed),
        "db_deleted": {
            "tasks": int(task_deleted),
            "task_runs": int(runs_deleted),
            "task_events": int(events_deleted),
            "task_artifacts": int(artifacts_deleted),
        },
    }

@router.get("/{task_id}/params")
def read_task_params(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get task parameters.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not task.params_object_key_current:
        params_key = f"tasks/{task_id}/params.json"
    else:
        params_key = task.params_object_key_current

    s3 = _create_s3_client()
    
    try:
        resp = s3.get_object(Bucket=settings.MINIO_BUCKET, Key=params_key)
        content = resp['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load params from storage: {e}")
        cached = _read_local_params_cache(task_id)
        return cached or {}

@router.post("/{task_id}/upload/complete")
def complete_upload(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Mark upload as complete.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    task.status = "UPLOADED"
    task.stage = "STAGE_2_PARAMS"
    db.add(task)
    db.commit()
    return {"status": "ok"}

@router.put("/{task_id}/params")
def update_task_params(
    task_id: str,
    params: Dict[str, Any] = Body(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Save task parameters to MinIO.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Define params key
    params_key = f"tasks/{task_id}/params.json"
    
    s3 = _create_s3_client()
    
    try:
        body = json.dumps(params, indent=2).encode("utf-8")
        sha256 = hashlib.sha256(body).hexdigest()
        s3.put_object(
            Bucket=settings.MINIO_BUCKET,
            Key=params_key,
            Body=body,
            ContentType="application/json",
            Metadata={"sha256": sha256},
        )

        try:
            run_base = settings.RUN_BASE_DIR
            cache_dir = os.path.join(run_base, str(task_id))
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "params.latest.json")
            cache_sha_path = os.path.join(cache_dir, "params.latest.sha256")
            with open(cache_path, "wb") as f:
                f.write(body)
            with open(cache_sha_path, "w", encoding="utf-8") as f:
                f.write(sha256)
        except Exception:
            logger.exception("Failed to write params cache task_id=%s", task_id)
        
        task.params_object_key_current = params_key
        db.commit()
        return {"status": "ok", "params_key": params_key, "sha256": sha256}
    except Exception as e:
        logger.error(f"Failed to save params: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_id}/params/storage")
def read_params_storage_status(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    params_key = task.params_object_key_current or f"tasks/{task_id}/params.json"

    s3 = _create_s3_client()

    result: dict[str, Any] = {"params_key": params_key, "exists": False}
    try:
        head = s3.head_object(Bucket=settings.MINIO_BUCKET, Key=params_key)
        meta = head.get("Metadata", {}) or {}
        result.update(
            {
                "exists": True,
                "bucket": settings.MINIO_BUCKET,
                "size": head.get("ContentLength"),
                "etag": (head.get("ETag") or "").strip('"'),
                "last_modified": head.get("LastModified").isoformat() if head.get("LastModified") else None,
                "sha256": meta.get("sha256"),
                "content_type": head.get("ContentType"),
            }
        )
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    try:
        cache_path = os.path.join(settings.RUN_BASE_DIR, str(task_id), "params.latest.json")
        cache_sha_path = os.path.join(settings.RUN_BASE_DIR, str(task_id), "params.latest.sha256")
        result["local_cache_exists"] = os.path.exists(cache_path)
        if os.path.exists(cache_path):
            result["local_cache_size"] = os.path.getsize(cache_path)
        if os.path.exists(cache_sha_path):
            with open(cache_sha_path, "r", encoding="utf-8") as f:
                result["local_cache_sha256"] = f.read().strip()
    except Exception:
        pass

    return result

@router.post("/{task_id}/debug/run")
def run_debug_task(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Load current params for snapshot
    params = {}
    if task.params_object_key_current:
        # We could fetch from MinIO, but QueueService might do it or we pass empty.
        # Ideally pass the snapshot.
        pass

    try:
        run_id = QueueService.submit_task(db, task, "debug", params_snapshot=params)
        return {"status": "queued", "run_id": run_id}
    except Exception as e:
        logger.error(f"Failed to submit debug task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/final/run")
def run_final_task(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    try:
        run_id = QueueService.submit_task(db, task, "final")
        return {"status": "queued", "run_id": run_id}
    except Exception as e:
        logger.error(f"Failed to submit final task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/stop")
def stop_task(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.cancel_requested = True
    db.commit()
    try:
        run_id = str(task.run_id_current) if getattr(task, "run_id_current", None) else ""
        images_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), "images")
        os.makedirs(images_dir, exist_ok=True)
        marker = f"cancel.{run_id}" if run_id else "cancel.global"
        marker_path = os.path.join(images_dir, marker)
        with open(marker_path, "a", encoding="utf-8"):
            pass
    except Exception:
        pass
    return {"status": "stop_requested"}

@router.get("/{task_id}/history")
def read_task_history(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
        
    runs = db.query(TaskRun).filter(TaskRun.task_id == task_id).order_by(TaskRun.created_at.desc()).all()
    return runs

def _is_run_active_status(status: Optional[str]) -> bool:
    if not status:
        return False
    status_upper = str(status).upper()
    return status_upper == "QUEUED" or status_upper.startswith("RUNNING")

def _delete_one_run(
    *,
    task_id: str,
    run_id: str,
    db: Session,
    current_user: User,
) -> dict[str, Any]:
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    try:
        run_uuid = uuid.UUID(str(run_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    run = (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id, TaskRun.id == run_uuid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if _is_run_active_status(run.status):
        raise HTTPException(status_code=409, detail="Run is active, stop it before deleting")

    run_base = getattr(settings, "RUN_BASE_DIR", "/data/runs")
    run_dir = os.path.join(run_base, str(task_id), str(run_id))
    local_existed = _safe_rmtree(base_dir=run_base, target_path=run_dir)
    if local_existed and os.path.exists(run_dir):
        raise HTTPException(status_code=500, detail="Failed to delete local run directory")

    if getattr(task, "run_id_current", None) == run_uuid:
        task.run_id_current = None

    run_deleted = (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id, TaskRun.id == run_uuid)
        .delete(synchronize_session=False)
    )

    return {"run_id": str(run_id), "deleted": bool(run_deleted), "local_dir_deleted": bool(local_existed)}

@router.delete("/{task_id}/history/{run_id}")
def delete_task_run(
    task_id: str,
    run_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    result = _delete_one_run(task_id=task_id, run_id=run_id, db=db, current_user=current_user)
    db.commit()
    return {"status": "deleted", **result}

@router.post("/{task_id}/history/delete")
def delete_task_runs_bulk(
    task_id: str,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    run_ids = payload.get("run_ids")
    if not isinstance(run_ids, list) or not run_ids:
        raise HTTPException(status_code=400, detail="run_ids must be a non-empty list")

    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for rid in run_ids:
        try:
            deleted.append(_delete_one_run(task_id=task_id, run_id=str(rid), db=db, current_user=current_user))
        except HTTPException as e:
            failed.append({"run_id": str(rid), "status_code": int(e.status_code), "detail": e.detail})
        except Exception as e:
            failed.append({"run_id": str(rid), "status_code": 500, "detail": f"{type(e).__name__}: {str(e)}"})

    db.commit()
    return {"status": "ok", "deleted": deleted, "failed": failed, "deleted_count": len(deleted), "failed_count": len(failed)}

@router.get("/{task_id}/history/{run_id}/log")
def read_run_log(
    task_id: str,
    run_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # Security check
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Construct log path: RUN_BASE_DIR/{task_id}/{run_id}/runtime.log
    # We need settings.RUN_BASE_DIR. If not in settings, assume default.
    run_base = getattr(settings, "RUN_BASE_DIR", "/data/runs") 
    log_path = os.path.join(run_base, task_id, run_id, "runtime.log")
    
    if not os.path.exists(log_path):
        return {"exists": False, "content": ""}
        
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"exists": True, "content": content}
    except Exception as e:
        return {"exists": True, "content": f"Error reading log: {e}"}

@router.get("/{task_id}/transfer/status")
def get_transfer_status(
    task_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Check current run transfer status
    if task.run_id_current:
        run_base = getattr(settings, "RUN_BASE_DIR", "/data/runs")
        status_path = os.path.join(run_base, task_id, str(task.run_id_current), "transfer_nd2.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
                
    # Fallback
    return {"state": "ready", "message": "Ready"}

@router.post("/{task_id}/transfer/cancel")
def cancel_transfer(task_id: str):
    return {"status": "ok"}

@router.get("/{task_id}/artifacts/list")
def list_run_artifacts(
    task_id: str,
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, effective_run_id, run_dir = _resolve_run_dir(task_id=task_id, run_id=run_id, db=db, current_user=current_user)
    output_dir = os.path.join(run_dir, "output")
    debug_dir = os.path.join(output_dir, "debug")
    final_dir = os.path.join(output_dir, "final")

    videos: list[dict[str, str]] = []
    csvs: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    def add_file(full_path: str, kind: str) -> None:
        abs_path = os.path.abspath(full_path)
        if abs_path in seen_paths:
            return
        seen_paths.add(abs_path)
        
        rel = os.path.relpath(full_path, run_dir)
        name = os.path.basename(full_path)
        if kind == "video":
            videos.append({"path": rel, "name": name})
        else:
            csvs.append({"path": rel, "name": name})

    for d in [debug_dir, final_dir, run_dir]:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                lower = fn.lower()
                if lower.endswith(".mp4") or lower.endswith(".avi"):
                    add_file(os.path.join(root, fn), "video")
                elif lower.endswith(".csv"):
                    add_file(os.path.join(root, fn), "csv")

    def score_video(item: dict[str, str]) -> tuple[int, int]:
        p = item["path"].lower()
        ext = 0 if p.endswith(".mp4") else 1
        pref = 0 if "output/debug/preview" in p else 1
        return (pref, ext)

    videos.sort(key=score_video)
    csvs.sort(key=lambda x: (0 if x["path"].lower().endswith("output/final/result.csv") else 1, x["path"].lower()))

    return {"run_id": effective_run_id, "videos": videos, "csvs": csvs}

@router.get("/{task_id}/artifacts/file")
def read_run_artifact_file(
    task_id: str,
    path: str,
    run_id: Optional[str] = Query(default=None),
    download: bool = Query(default=False),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, effective_run_id, run_dir = _resolve_run_dir(task_id=task_id, run_id=run_id, db=db, current_user=current_user)
    full_path = _safe_join(run_dir, path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    lower = full_path.lower()
    media_type = "application/octet-stream"
    if lower.endswith(".mp4"):
        media_type = "video/mp4"
    elif lower.endswith(".avi"):
        media_type = "video/x-msvideo"
    elif lower.endswith(".csv"):
        media_type = "text/csv"
    elif lower.endswith(".json"):
        media_type = "application/json"

    filename = os.path.basename(full_path)
    return FileResponse(
        full_path,
        media_type=media_type,
        filename=filename if download else None,
    )

@router.get("/{task_id}/preview/download")
def download_preview_video(
    task_id: str,
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, effective_run_id, run_dir = _resolve_run_dir(task_id=task_id, run_id=run_id, db=db, current_user=current_user)
    candidates = [
        os.path.join(run_dir, "output", "debug", "preview.mp4"),
        os.path.join(run_dir, "output", "debug", "preview.avi"),
    ]
    chosen = next((p for p in candidates if os.path.exists(p)), None)
    if not chosen:
        raise HTTPException(status_code=404, detail="Preview not found")
    media_type = "video/mp4" if chosen.lower().endswith(".mp4") else "video/x-msvideo"
    return FileResponse(chosen, media_type=media_type, filename=os.path.basename(chosen))

@router.get("/{task_id}/results/download")
def download_results_csv(
    task_id: str,
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, effective_run_id, run_dir = _resolve_run_dir(task_id=task_id, run_id=run_id, db=db, current_user=current_user)
    candidates = [
        os.path.join(run_dir, "output", "final", "AllXYResults.csv"),
        os.path.join(run_dir, "output", "final", "result.csv"),
        os.path.join(run_dir, "AllXYResults.csv"),
    ]
    chosen = next((p for p in candidates if os.path.exists(p)), None)
    if not chosen:
        for root, _, files in os.walk(run_dir):
            for fn in files:
                if fn.lower().endswith(".csv"):
                    chosen = os.path.join(root, fn)
                    break
            if chosen:
                break
    if not chosen:
        raise HTTPException(status_code=404, detail="Result CSV not found")
    return FileResponse(chosen, media_type="text/csv", filename=os.path.basename(chosen))

# --- Multipart Upload Proxy Endpoints (Bypass CORS) ---

@router.get("/{task_id}/multipart/proxy/status")
def multipart_upload_proxy_status(
    task_id: str,
    upload_id: str = Query(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    s3 = _create_s3_client()
    try:
        parts: list[dict[str, Any]] = []
        part_marker: Optional[int] = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": settings.MINIO_BUCKET,
                "Key": task.nd2_object_key,
                "UploadId": upload_id,
                "MaxParts": 1000,
            }
            if part_marker is not None:
                kwargs["PartNumberMarker"] = part_marker
            resp = s3.list_parts(**kwargs)
            for p in resp.get("Parts") or []:
                pn = int(p.get("PartNumber") or 0)
                etag = str(p.get("ETag") or "").replace('"', "")
                if pn > 0 and etag:
                    parts.append({"PartNumber": pn, "ETag": etag})
            if not resp.get("IsTruncated"):
                break
            part_marker = resp.get("NextPartNumberMarker")
            if part_marker is None:
                break
        max_part = max([p["PartNumber"] for p in parts], default=0)
        return {"exists": True, "upload_id": upload_id, "parts": parts, "max_part": max_part}
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        if code == "NoSuchUpload":
            raise HTTPException(status_code=409, detail={"code": "NoSuchUpload", "message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/multipart/proxy/init")
def init_multipart_upload_proxy(
    task_id: str,
    payload: dict | None = Body(None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)

    s3 = _create_s3_client()

    try:
        resp = s3.create_multipart_upload(Bucket=settings.MINIO_BUCKET, Key=task.nd2_object_key)
        upload_id = resp["UploadId"]

        _cleanup_upload_state(task_id)
        chunk_size = int((payload or {}).get("chunk_size") or 0)
        total_parts = int((payload or {}).get("total_parts") or 0)
        file_size = int((payload or {}).get("file_size") or (task.nd2_size or 0))
        _set_upload_meta(
            task_id,
            {
                "upload_id": upload_id,
                "chunk_size": chunk_size,
                "total_parts": total_parts,
                "file_size": file_size,
                "uploaded_bytes": 0,
                "progress": 0,
                "paused": 0,
                "status": "uploading",
                "updated_at": int(time.time()),
            },
        )

        if task.status == "DRAFT":
            task.status = "UPLOADING"
        task.progress = 0
        db.add(task)
        db.commit()

        return {"upload_id": upload_id}
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        logger.error(f"Proxy Init Error: {e}")
        raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})

@router.put("/{task_id}/multipart/proxy/part")
async def upload_part_proxy(
    task_id: str,
    upload_id: str,
    part_number: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    logger.info(f"Proxy Part Upload Start: Task={task_id}, Part={part_number}")
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    if _is_upload_paused(task_id):
        raise HTTPException(status_code=409, detail={"code": "UploadPaused", "message": "Upload paused"})
    
    s3 = _create_s3_client()
    
    try:
        # Note: This reads entire body into memory. For large concurrency, stream processing is better.
        # But with 10MB chunks, it should be manageable.
        body = await request.body()
        size = len(body)
        logger.info(f"Proxy Part Received Body: {size} bytes")

        resp = s3.upload_part(
            Bucket=settings.MINIO_BUCKET,
            Key=task.nd2_object_key,
            PartNumber=part_number,
            UploadId=upload_id,
            Body=body
        )
        logger.info(f"Proxy Part Uploaded to MinIO: ETag={resp.get('ETag')}")
        etag = str(resp.get("ETag") or "").replace('"', "")

        r = _get_redis()
        parts_key = _upload_parts_key(task_id)
        meta_key = _upload_meta_key(task_id)
        r.expire(parts_key, 7 * 24 * 3600)
        added = r.sadd(parts_key, int(part_number))
        if int(added) == 1:
            r.hincrby(meta_key, "uploaded_bytes", int(size))
        meta = _get_upload_meta(task_id)
        file_size = int(meta.get("file_size") or (task.nd2_size or 0) or 0)
        uploaded_bytes = int(meta.get("uploaded_bytes") or 0)
        progress = int(meta.get("progress") or 0)
        if file_size > 0:
            progress = max(progress, min(99, int((uploaded_bytes / file_size) * 100)))
        _set_upload_meta(task_id, {"upload_id": upload_id, "status": "uploading", "progress": progress, "updated_at": int(time.time())})
        _maybe_update_task_progress(db, task, task_id, progress)

        return {"ETag": etag}
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        logger.error(f"Proxy Part Error: {e}")
        if code == "NoSuchUpload":
            raise HTTPException(status_code=409, detail={"code": "NoSuchUpload", "message": str(e)})
        raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})
    except Exception as e:
        logger.error(f"Proxy Part Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/multipart/proxy/complete")
def complete_multipart_upload_proxy(
    task_id: str,
    payload: dict = Body(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
        
    s3 = _create_s3_client()

    upload_id = payload['upload_id']
    parts = payload['parts']
    
    sorted_parts = sorted(parts, key=lambda x: x['PartNumber'])
    
    try:
        s3.complete_multipart_upload(
            Bucket=settings.MINIO_BUCKET,
            Key=task.nd2_object_key,
            UploadId=upload_id,
            MultipartUpload={'Parts': sorted_parts}
        )
        _set_upload_meta(task_id, {"status": "completed", "progress": 100, "updated_at": int(time.time())})
        task.progress = 100
        db.add(task)
        db.commit()
        return {"status": "ok"}
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        logger.error(f"Proxy Complete Error: {e}")
        if code == "NoSuchUpload":
            raise HTTPException(status_code=409, detail={"code": "NoSuchUpload", "message": str(e)})
        raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})
    except Exception as e:
        logger.error(f"Proxy Complete Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/multipart/proxy/abort")
def abort_multipart_upload_proxy(
    task_id: str,
    payload: dict | None = Body(None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    task = _get_task_or_404(task_id=task_id, db=db, current_user=current_user)
    upload_id = str((payload or {}).get("upload_id") or (_get_upload_meta(task_id).get("upload_id") or ""))
    if not upload_id:
        raise HTTPException(status_code=400, detail="Missing upload_id")
    s3 = _create_s3_client()
    try:
        s3.abort_multipart_upload(Bucket=settings.MINIO_BUCKET, Key=task.nd2_object_key, UploadId=upload_id)
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code") or ""
        if code != "NoSuchUpload":
            raise HTTPException(status_code=500, detail={"code": code, "message": str(e)})
    _cleanup_upload_state(task_id)
    task.progress = 0
    if task.stage == "STAGE_1_UPLOAD":
        task.status = "DRAFT"
    db.add(task)
    db.commit()
    return {"status": "ok"}
