from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.services.minio_service import MinioService
from app.db.models import SystemStat, AppConfig, User
from app.db.session import SessionLocal
from app.api import deps
from app.schemas import SystemStatOut, AppConfigOut, AppConfigCreate, AppConfigUpdate
import uuid
import json
import os
import time
import logging
import threading
import socket
import psutil
import platform
from typing import List, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

router = APIRouter()

class PipelineInfo(BaseModel):
    path: str
    name: str
    is_valid: bool
    version: str

class PipelineValidationRequest(BaseModel):
    path: str

# Background task for collecting stats
_stats_thread_started = False
_last_alert_time = {} # Key: alert_type, Value: timestamp

def check_and_alert(db: Session, stat: SystemStat):
    global _last_alert_time
    
    # Get thresholds from config
    cpu_threshold_config = db.query(AppConfig).filter(AppConfig.key == "system.cpu_threshold").first()
    memory_threshold_config = db.query(AppConfig).filter(AppConfig.key == "system.memory_threshold").first()
    disk_threshold_config = db.query(AppConfig).filter(AppConfig.key == "system.disk_threshold").first()
    
    cpu_threshold = float(cpu_threshold_config.value) if cpu_threshold_config else 90.0
    memory_threshold = float(memory_threshold_config.value) if memory_threshold_config else 90.0
    disk_threshold = float(disk_threshold_config.value) if disk_threshold_config else 90.0
    
    # Alert logic
    alerts = []
    if stat.cpu_percent > cpu_threshold:
        alerts.append(f"CPU usage high: {stat.cpu_percent}% (Threshold: {cpu_threshold}%)")
    
    if stat.memory_percent > memory_threshold:
        alerts.append(f"Memory usage high: {stat.memory_percent}% (Threshold: {memory_threshold}%)")
        
    if stat.disk_percent > disk_threshold:
        alerts.append(f"Disk usage high: {stat.disk_percent}% (Threshold: {disk_threshold}%)")
        
    if alerts:
        now = datetime.utcnow()
        # Simple cooldown mechanism: 1 hour per alert type (or just global cooldown for simplicity)
        last_time = _last_alert_time.get("resource_alert")
        if not last_time or (now - last_time) > timedelta(minutes=60):
            # Send alert to logs instead of database messages
            message_content = "System Alert:\n" + "\n".join(alerts)
            logging.warning(message_content)
            
            _last_alert_time["resource_alert"] = now
            print(f"System alert logged: {message_content}")

def collect_stats_loop():
    while True:
        try:
            db = SessionLocal()
            cpu_percent = psutil.cpu_percent(interval=None) # Non-blocking first call usually 0, but okay for loop
            # But we want accuracy, so maybe interval=1 is better, but it blocks. 
            # Since this is a thread, blocking is fine.
            cpu_percent = psutil.cpu_percent(interval=1)
            
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            net = psutil.net_io_counters()
            
            stat = SystemStat(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_percent=disk.percent,
                net_sent=net.bytes_sent,
                net_recv=net.bytes_recv,
                ts=datetime.utcnow()
            )
            db.add(stat)
            
            # Check for alerts
            check_and_alert(db, stat)
            
            # Cleanup old stats (keep last 24 hours = 1440 minutes)
            # This might be heavy if table is huge, so do it occasionally or just delete older than X
            cutoff = datetime.utcnow() - timedelta(hours=24)
            db.query(SystemStat).filter(SystemStat.ts < cutoff).delete()
            
            db.commit()
            db.close()
            
            # Sleep for 59 seconds (since cpu_percent took 1s)
            time.sleep(59)
        except Exception as e:
            print(f"Error collecting stats: {e}")
            time.sleep(60)

def start_stats_collection():
    global _stats_thread_started
    if not _stats_thread_started:
        t = threading.Thread(target=collect_stats_loop, daemon=True)
        t.start()
        _stats_thread_started = True

@router.get("/history", response_model=List[SystemStatOut])
def get_system_history(
    db: Session = Depends(deps.get_db),
    limit: int = 60
):
    """
    Get system resource usage history.
    """
    stats = db.query(SystemStat).order_by(desc(SystemStat.ts)).limit(limit).all()
    # Reverse to get chronological order
    return stats[::-1]



def _parse_endpoint(endpoint: str) -> tuple[str, Optional[int]]:
    if endpoint.startswith("http://"):
        endpoint = endpoint[len("http://") :]
    elif endpoint.startswith("https://"):
        endpoint = endpoint[len("https://") :]

    endpoint = endpoint.strip().rstrip("/")

    if endpoint.startswith("["):
        end = endpoint.find("]")
        host = endpoint[1:end] if end != -1 else endpoint
        rest = endpoint[end + 1 :] if end != -1 else ""
        if rest.startswith(":"):
            try:
                return host, int(rest[1:])
            except ValueError:
                return host, None
        return host, None

    if ":" in endpoint:
        host, port_str = endpoint.rsplit(":", 1)
        try:
            return host, int(port_str)
        except ValueError:
            return host, None

    return endpoint, None


def _resolve_ips(host: str) -> list[str]:
    ips: list[str] = []
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return ips
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if ip not in ips:
            ips.append(ip)
    return ips


def _tcp_probe(ip: str, port: int, timeout_sec: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        sock = socket.create_connection((ip, port), timeout=timeout_sec)
        sock.close()
        return {"ip": ip, "ok": True, "ms": int((time.perf_counter() - started) * 1000)}
    except Exception as e:
        return {
            "ip": ip,
            "ok": False,
            "ms": int((time.perf_counter() - started) * 1000),
            "error": f"{type(e).__name__}: {str(e)}",
        }


@router.get("/minio/health")
def minio_health():
    endpoint = settings.MINIO_ENDPOINT
    host, port = _parse_endpoint(endpoint)
    port = port or (443 if settings.MINIO_SECURE else 80)

    resolved_ips = _resolve_ips(host)
    probes = [_tcp_probe(ip, port, timeout_sec=0.8) for ip in resolved_ips[:8]]

    result: dict[str, Any] = {
        "ok": False,
        "endpoint": endpoint,
        "secure": settings.MINIO_SECURE,
        "bucket": settings.MINIO_BUCKET,
        "resolved_ips": resolved_ips,
        "tcp_probes": probes,
        "checks": {},
    }

    minio = MinioService(
        endpoint=endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        bucket=settings.MINIO_BUCKET,
        presign_expires_sec=min(300, settings.MINIO_PRESIGN_EXPIRES_SECONDS),
        connect_timeout_sec=min(2, settings.MINIO_HTTP_CONNECT_TIMEOUT_SECONDS),
        read_timeout_sec=5,
    )

    presign_key = f"health/{uuid.uuid4().hex}.txt"
    t0 = time.perf_counter()
    try:
        _ = minio.presign_put(presign_key, expires_sec=60)
        result["checks"]["presign_put"] = {"ok": True, "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        result["checks"]["presign_put"] = {
            "ok": False,
            "ms": int((time.perf_counter() - t0) * 1000),
            "error": f"{type(e).__name__}: {str(e)}",
        }

    t1 = time.perf_counter()
    try:
        exists = minio.client.bucket_exists(minio.bucket)
        result["checks"]["bucket_exists"] = {
            "ok": bool(exists),
            "ms": int((time.perf_counter() - t1) * 1000),
        }
    except Exception as e:
        result["checks"]["bucket_exists"] = {
            "ok": False,
            "ms": int((time.perf_counter() - t1) * 1000),
            "error": f"{type(e).__name__}: {str(e)}",
        }

    result["ok"] = bool(result["checks"].get("presign_put", {}).get("ok")) and bool(
        result["checks"].get("bucket_exists", {}).get("ok")
    )
    return result


@router.get("/stats")
def system_stats():
    """
    Get system resource usage (CPU, RAM, Disk).
    """
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    # Disk usage (handle Windows/Linux path)
    disk_path = "C:\\" if platform.system() == "Windows" else "/"
    # Or better, use current drive
    disk_path = os.path.abspath(os.sep)
    
    disk = psutil.disk_usage(disk_path)
    
    # Platform info
    uname = platform.uname()
    
    return {
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count(),
        },
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent,
            "used": memory.used,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "platform": {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor,
        },
        "timestamp": time.time()
    }

# --- App Config Endpoints ---

@router.get("/version")
def get_system_version(
    db: Session = Depends(deps.get_db),
):
    """
    Get system version from PIPELINE_ROOT directory name.
    Prioritizes 'system.pipeline_root' from AppConfig, falls back to settings.
    """
    try:
        pipeline_root = settings.PIPELINE_ROOT
        
        # Check DB config override
        config = db.query(AppConfig).filter(AppConfig.key == "system.pipeline_root").first()
        if config and config.value:
            # Only use config if path exists, otherwise fallback to default
            if os.path.exists(config.value):
                pipeline_root = config.value
            else:
                # Optional: Update DB or just ignore? ignoring is safer for read-only endpoint
                # But we want to return a valid root if possible
                pass

        if pipeline_root:
            return {
                "version": os.path.basename(pipeline_root),
                "pipeline_root": pipeline_root
            }
        return {"version": "Unknown", "pipeline_root": ""}
    except Exception:
        return {"version": "Unknown", "pipeline_root": ""}

@router.get("/pipelines", response_model=List[PipelineInfo])
def list_pipelines(
    current_user: User = Depends(deps.get_current_user_admin),
):
    """
    Scan for available MATLAB pipelines in the MATLAB_Package directory.
    """
    base_dir = "/app/matlab_packages"
    
    pipelines = []
    if os.path.exists(base_dir):
        try:
            for name in os.listdir(base_dir):
                full_path = os.path.join(base_dir, name)
                if os.path.isdir(full_path):
                    # Check for GUV_Pipeline.m or generic GUV structure
                    is_valid = os.path.exists(os.path.join(full_path, "GUV_Pipeline.m"))
                    
                    # Heuristic: include if it has "GUV" in name or is valid
                    if is_valid or ("GUV" in name and os.path.isdir(os.path.join(full_path, "functions"))):
                         pipelines.append({
                             "path": full_path,
                             "name": name,
                             "is_valid": is_valid,
                             "version": name
                         })
        except Exception as e:
            print(f"Error scanning pipelines: {e}")
            
    return pipelines

@router.post("/pipelines/validate")
def validate_pipeline(
    request: PipelineValidationRequest,
    current_user: User = Depends(deps.get_current_user_admin),
):
    """
    Validate if a path is a valid MATLAB pipeline.
    """
    path = request.path.strip()
    if not os.path.exists(path):
        return {"valid": False, "error": "Path does not exist"}
    
    if not os.path.isdir(path):
        return {"valid": False, "error": "Path is not a directory"}
        
    required_files = ["GUV_Pipeline.m"]
    missing = [f for f in required_files if not os.path.exists(os.path.join(path, f))]
    
    if missing:
        return {"valid": False, "error": f"Missing required files: {', '.join(missing)}"}
    
    # Check for functions dir
    if not os.path.isdir(os.path.join(path, "functions")):
         return {"valid": False, "error": "Missing 'functions' directory"}

    return {"valid": True, "version": os.path.basename(path)}

@router.get("/config", response_model=List[AppConfigOut])
def read_configs(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user_admin),
):
    configs = db.query(AppConfig).all()
    return configs

@router.post("/config", response_model=AppConfigOut)
def create_config(
    config_in: AppConfigCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    existing = db.query(AppConfig).filter(AppConfig.key == config_in.key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Config key already exists")
    
    config = AppConfig(**config_in.dict())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config

@router.put("/config/{key}", response_model=AppConfigOut)
def update_config(
    key: str,
    config_in: AppConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    config = db.query(AppConfig).filter(AppConfig.key == key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    if config_in.value is not None:
        config.value = config_in.value
    if config_in.description is not None:
        config.description = config_in.description
    
    db.commit()
    db.refresh(config)
    return config

@router.delete("/config/{key}")
def delete_config(
    key: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    config = db.query(AppConfig).filter(AppConfig.key == key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    db.delete(config)
    db.commit()
    return {"ok": True}
