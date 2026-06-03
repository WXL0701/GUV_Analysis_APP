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
_cold_archive_transfer_semaphore = threading.Semaphore(1)
_java_nd2_helper_compile_lock = threading.Lock()

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

def _copy_file_atomic(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = f"{dst}.tmp.{uuid.uuid4().hex}"
    with open(src, "rb") as fsrc, open(tmp, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst, length=16 * 1024 * 1024)
    os.replace(tmp, dst)

def _find_ffmpeg() -> Optional[str]:
    system_ffmpeg = "/usr/bin/ffmpeg"
    if os.path.exists(system_ffmpeg) and os.access(system_ffmpeg, os.X_OK):
        return system_ffmpeg
    return shutil.which("ffmpeg")

def _clean_video_tool_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "DYLD_LIBRARY_PATH"):
        env.pop(key, None)
    env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    return env

def _debug_preview_mp4_path(video_path: str) -> str:
    directory = os.path.dirname(video_path)
    stem, _ = os.path.splitext(os.path.basename(video_path))
    return os.path.join(directory, f"{stem}.mp4")

def _collect_debug_avi_videos(run_dir: str) -> list[str]:
    debug_dir = os.path.join(run_dir, "output", "debug")
    if not os.path.isdir(debug_dir):
        return []
    videos: list[str] = []
    for root, _, files in os.walk(debug_dir):
        for fn in files:
            if fn.lower().endswith(".avi"):
                videos.append(os.path.join(root, fn))
    return sorted(videos)

def _transcode_debug_video_to_mp4(src_path: str, dst_path: str, log_file: str, max_px: int = 720) -> bool:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        _append_runtime_log(log_file, "WARN: ffmpeg not found, skip debug video browser-compatible MP4 generation")
        return False

    try:
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0 and os.path.getmtime(dst_path) >= os.path.getmtime(src_path):
            _append_runtime_log(log_file, f"Debug video MP4 already exists: {dst_path}")
            return True
    except Exception:
        pass

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    tmp_path = f"{dst_path}.tmp.{uuid.uuid4().hex}.mp4"
    max_px = max(240, min(int(max_px or 720), 1080))
    vf = (
        "scale="
        f"w='if(gte(iw,ih),min({max_px},iw),-2)':"
        f"h='if(gte(ih,iw),min({max_px},ih),-2)'"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        src_path,
        "-map",
        "0:v:0",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        tmp_path,
    ]

    _append_runtime_log(log_file, f"Generating browser-compatible debug MP4: {os.path.basename(src_path)} -> {os.path.basename(dst_path)} max_px={max_px}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
            env=_clean_video_tool_env(),
        )
        if result.returncode != 0:
            detail = (result.stdout or "").strip()
            _append_runtime_log(log_file, f"WARN: Debug video MP4 generation failed: {detail[-2000:]}")
            return False
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) <= 0:
            _append_runtime_log(log_file, "WARN: Debug video MP4 generation produced no output")
            return False
        os.replace(tmp_path, dst_path)
        _append_runtime_log(log_file, f"Debug video MP4 ready: {dst_path}")
        return True
    except subprocess.TimeoutExpired:
        _append_runtime_log(log_file, "WARN: Debug video MP4 generation timed out")
        return False
    except Exception as e:
        _append_runtime_log(log_file, f"WARN: Debug video MP4 generation skipped: {type(e).__name__}: {str(e)}")
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def _postprocess_debug_videos(run_dir: str, log_file: str, max_px: int = 720) -> dict[str, int]:
    avi_videos = _collect_debug_avi_videos(run_dir)
    if not avi_videos:
        _append_runtime_log(log_file, "Debug video postprocess: no AVI files found")
        return {"found": 0, "converted": 0}

    converted = 0
    for src_path in avi_videos:
        dst_path = _debug_preview_mp4_path(src_path)
        try:
            if _transcode_debug_video_to_mp4(src_path, dst_path, log_file, max_px=max_px):
                converted += 1
        except Exception as e:
            _append_runtime_log(log_file, f"WARN: Debug video postprocess failed for {src_path}: {type(e).__name__}: {str(e)}")
    _append_runtime_log(log_file, f"Debug video postprocess done: found={len(avi_videos)} converted={converted}")
    return {"found": len(avi_videos), "converted": converted}

def _bioformats_jar_path() -> str:
    candidates = [
        os.path.join(str(settings.BFMATLAB_ROOT), "bioformats_package.jar"),
        "/home/bfmatlab/bioformats_package.jar",
        "/opt/bfmatlab/bioformats_package.jar",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise RuntimeError("bioformats_package.jar is not available")

def _ensure_java_nd2_helper_compiled() -> tuple[str, str]:
    script_dir = os.path.join(os.getcwd(), "scripts")
    source_path = os.path.join(script_dir, "java", "Nd2PreviewHelper.java")
    class_dir = os.path.join(settings.RUN_BASE_DIR, ".java_nd2_preview_classes")
    class_file = os.path.join(class_dir, "Nd2PreviewHelper.class")
    jar_path = _bioformats_jar_path()
    if not os.path.isfile(source_path):
        raise RuntimeError("Java ND2 helper source is missing")
    os.makedirs(class_dir, exist_ok=True)
    with _java_nd2_helper_compile_lock:
        source_mtime = os.path.getmtime(source_path)
        class_mtime = os.path.getmtime(class_file) if os.path.exists(class_file) else 0
        if class_mtime >= source_mtime:
            return class_dir, jar_path
        javac = shutil.which("javac")
        if not javac:
            raise RuntimeError("javac is not available")
        result = subprocess.run(
            [javac, "-cp", jar_path, "-d", class_dir, source_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Java ND2 helper compile failed: {(result.stdout or '')[-2000:]}")
    return class_dir, jar_path

def _run_java_nd2_helper(args: list[str], timeout: int = 600) -> None:
    class_dir, jar_path = _ensure_java_nd2_helper_compiled()
    classpath = os.pathsep.join([class_dir, jar_path])
    result = subprocess.run(
        ["java", "-cp", classpath, "Nd2PreviewHelper", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Java ND2 helper failed: {(result.stdout or '')[-3000:]}")

def _load_nd2_metadata_for_video(task_id: str, nd2_path: str, run_dir: str) -> dict[str, Any]:
    meta_path = os.path.join(run_dir, "nd2.metadata.json")
    _run_java_nd2_helper(["metadata", nd2_path, meta_path], timeout=180)
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _video_color_to_lut(color: Any, fallback: str) -> str:
    vals = _as_list(color)
    if len(vals) >= 3:
        try:
            r, g, b = [float(vals[i]) for i in range(3)]
            if g >= r and g >= b:
                return "green"
            if r >= g and r >= b and b >= 0.4:
                return "magenta"
            if b >= r and b >= g and g >= 0.4:
                return "cyan"
            if r >= g and r >= b:
                return "red"
        except Exception:
            pass
    return fallback

def _video_contrast_value(video: dict[str, Any], key: str, index: int) -> str:
    values = _as_list((video.get("Contrast") or {}).get(key))
    if len(values) > index:
        try:
            return str(float(values[index]))
        except Exception:
            return "auto"
    return "auto"

def _normalize_video_params(params: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    video = dict(params.get("Video") or {})
    series_meta = metadata.get("series") if isinstance(metadata.get("series"), list) else []
    series_count = len(series_meta)
    series_list = [int(v) for v in _as_list(video.get("SeriesList")) if str(v).strip() != ""]
    if not series_list:
        series_indexes = list(range(series_count))
    else:
        # Accept both UI-style 1-based and internal 0-based values. If any zero is present, treat as 0-based.
        if any(v == 0 for v in series_list):
            series_indexes = [v for v in series_list if 0 <= v < series_count]
        else:
            series_indexes = [v - 1 for v in series_list if 1 <= v <= series_count]
    tasks = [str(v).strip() for v in _as_list(video.get("Tasks")) if str(v).strip()]
    if not tasks:
        tasks = ["Merge"]
    normalized_tasks: list[str] = []
    for task in tasks:
        t = task.lower()
        if t in ("c1", "c01", "ref"):
            normalized_tasks.append("C1")
        elif t in ("c2", "c02", "oth"):
            normalized_tasks.append("C2")
        elif t == "merge":
            normalized_tasks.append("Merge")
    if not normalized_tasks:
        normalized_tasks = ["Merge"]
    frame_range = [int(v) for v in _as_list(video.get("FrameRange")) if str(v).strip() != ""]
    max_px = max(240, min(int(video.get("MaxPx") or 720), 4096))
    fps = max(1, min(int(video.get("FPS") or 10), 60))
    quality = max(1, min(int(video.get("Quality") or 90), 100))
    crf = max(18, min(32, int(round(34 - (quality * 0.16)))))
    scale_bar = dict(video.get("ScaleBar") or {})
    timestamp = dict(video.get("TimeStamp") or {})
    return {
        "video": video,
        "series_indexes": series_indexes,
        "tasks": normalized_tasks,
        "frame_range": frame_range,
        "max_px": max_px,
        "fps": fps,
        "crf": crf,
        "lut1": _video_color_to_lut((video.get("Color") or {}).get("C1"), "green"),
        "lut2": _video_color_to_lut((video.get("Color") or {}).get("C2"), "red"),
        "c1_min": _video_contrast_value(video, "C1", 0),
        "c1_max": _video_contrast_value(video, "C1", 1),
        "c2_min": _video_contrast_value(video, "C2", 0),
        "c2_max": _video_contrast_value(video, "C2", 1),
        "scale_bar": scale_bar,
        "timestamp": timestamp,
    }

def _video_task_suffix(task_name: str) -> str:
    return "MERGE" if task_name == "Merge" else task_name.upper().replace("C", "C0")

def _encode_video_frames(frame_dir: str, out_path: str, fps: int, crf: int, log_file: str) -> None:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    tmp_path = f"{out_path}.tmp.{uuid.uuid4().hex}.mp4"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(frame_dir, "frame_%06d.png"),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        tmp_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800, env=_clean_video_tool_env())
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg video encode failed: {(result.stdout or '')[-3000:]}")
    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) <= 0:
        raise RuntimeError("ffmpeg video encode produced no output")
    os.replace(tmp_path, out_path)
    _append_runtime_log(log_file, f"Video MP4 ready: {out_path}")

def _render_video_frames(
    *,
    nd2_path: str,
    frame_dir: str,
    series: int,
    size_t: int,
    task_name: str,
    cfg: dict[str, Any],
    metadata_series: dict[str, Any],
    params: dict[str, Any],
    log_file: str,
) -> int:
    frame_range = cfg["frame_range"]
    start = 0
    end = max(0, int(size_t) - 1)
    if len(frame_range) >= 2:
        start = max(0, int(frame_range[0]) - 1)
        end = min(end, int(frame_range[1]) - 1)
    if end < start:
        raise RuntimeError(f"Invalid frame range start={start + 1} end={end + 1}")

    scale_bar = cfg["scale_bar"]
    timestamp = cfg["timestamp"]
    pixel_size = scale_bar.get("PixelSize_um")
    if pixel_size in (None, "", []):
        pixel_size = metadata_series.get("pixel_size_um") or params.get("PixelSize_um")
    if pixel_size in (None, "", []):
        pixel_size = "NaN"
        if bool(scale_bar.get("Enable", True)):
            _append_runtime_log(log_file, f"WARN: Scale bar skipped for series={series} because pixel size is unknown")
    interval = timestamp.get("Interval_s")
    if interval in (None, "", []):
        interval = params.get("FrameInterval_s")
    if interval in (None, "", []):
        interval = "NaN"

    mode = "merge" if task_name == "Merge" else "single"
    c1 = 0 if task_name != "C2" else 1
    c2 = 1
    lut1 = cfg["lut1"] if task_name != "C2" else cfg["lut2"]
    lut2 = cfg["lut2"]
    min_value = cfg["c1_min"] if task_name != "C2" else cfg["c2_min"]
    max_value = cfg["c1_max"] if task_name != "C2" else cfg["c2_max"]
    if task_name == "Merge":
        min_value = cfg["c1_min"]
        max_value = cfg["c1_max"]

    os.makedirs(frame_dir, exist_ok=True)
    _run_java_nd2_helper(
        [
            "videoFrames",
            nd2_path,
            frame_dir,
            str(series),
            "0",
            str(c1),
            str(c2),
            str(start),
            str(end),
            mode,
            lut1,
            lut2,
            str(min_value),
            str(max_value),
            str(cfg["max_px"]),
            "1" if bool(scale_bar.get("Enable", True)) and str(pixel_size) != "NaN" else "0",
            str(scale_bar.get("Length_um") or 50),
            str(pixel_size),
            "1" if bool(timestamp.get("Enable", True)) else "0",
            str(timestamp.get("StartFrame") or 1),
            str(interval),
            str(timestamp.get("Unit") or "min"),
            "1" if bool(timestamp.get("ShowFrameNumber", True)) else "0",
        ],
        timeout=max(600, (end - start + 1) * 20),
    )
    return end - start + 1

@celery_app.task(bind=True)
def run_video_task(self, task_id: str, run_id: str):
    db = SessionLocal()
    run_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), str(run_id))
    log_file = os.path.join(run_dir, "runtime.log")
    task_run: Optional[TaskRun] = None
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"status": "failed", "error": "Task not found"}
        run_uuid = uuid.UUID(str(run_id))
        task_run = db.query(TaskRun).filter(TaskRun.id == run_uuid, TaskRun.task_id == task_id).first()
        os.makedirs(os.path.join(run_dir, "output", "video"), exist_ok=True)
        os.makedirs(os.path.join(run_dir, "logs"), exist_ok=True)
        _append_runtime_log(log_file, f"Worker started. mode=video task_id={task_id} run_id={run_id}")
        if task_run:
            task_run.started_at = datetime.utcnow()
            task_run.status = "RUNNING"
        task.status = "RUNNING_VIDEO"
        task.last_error = None
        db.commit()

        images_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), "images")
        os.makedirs(images_dir, exist_ok=True)
        original_filename = os.path.basename(str(task.nd2_object_key or "input.nd2"))
        if not original_filename.lower().endswith(".nd2"):
            original_filename += ".nd2"
        cached_nd2_path = os.path.join(images_dir, original_filename)
        minio = get_minio_service()
        cached_nd2_path = _ensure_hot_nd2(
            task=task,
            task_id=str(task_id),
            run_id=str(run_id),
            minio=minio,
            nd2_key=str(task.nd2_object_key),
            cached_nd2_path=cached_nd2_path,
            images_dir=images_dir,
            run_dir=run_dir,
            db=db,
            log_file=log_file,
        )

        params_key = task.params_object_key_current or f"tasks/{task_id}/params.json"
        params_path, _params_source = _sync_params_to_run_dir(
            task_id=str(task_id),
            run_id=str(run_id),
            minio=minio,
            params_key=str(params_key),
            run_dir=run_dir,
            log_file=log_file,
        )
        with open(params_path, "r", encoding="utf-8") as f:
            params = json.load(f)
        metadata = _load_nd2_metadata_for_video(str(task_id), str(cached_nd2_path), run_dir)
        cfg = _normalize_video_params(params, metadata)
        video_params_path = os.path.join(run_dir, "video.params.json")
        _write_json_atomic(video_params_path, {"Video": cfg["video"], "normalized": {k: v for k, v in cfg.items() if k not in ("video", "scale_bar", "timestamp")}})
        if task_run:
            task_run.params_snapshot = params
            db.commit()

        series_meta = metadata.get("series") if isinstance(metadata.get("series"), list) else []
        total_jobs = len(cfg["series_indexes"]) * len(cfg["tasks"])
        done_jobs = 0
        if total_jobs <= 0:
            raise RuntimeError("No video jobs selected")

        for series in cfg["series_indexes"]:
            if _should_cancel(str(task_id), str(run_id), run_dir, images_dir, db):
                raise RuntimeError("Video run canceled")
            meta = series_meta[series] if 0 <= series < len(series_meta) else {}
            size_t = int(meta.get("size_t") or 1)
            size_c = int(meta.get("size_c") or 1)
            for task_name in cfg["tasks"]:
                if task_name in ("C2", "Merge") and size_c < 2:
                    _append_runtime_log(log_file, f"WARN: Skip {task_name} for XY{series + 1:03d}; ND2 has only {size_c} channel(s)")
                    done_jobs += 1
                    continue
                if _should_cancel(str(task_id), str(run_id), run_dir, images_dir, db):
                    raise RuntimeError("Video run canceled")
                suffix = _video_task_suffix(task_name)
                frame_dir = os.path.join(run_dir, "output", "video_frames", f"XY{series + 1:03d}_{suffix}")
                out_path = os.path.join(run_dir, "output", "video", f"XY{series + 1:03d}_{suffix}.mp4")
                _append_runtime_log(log_file, f"VIDEO_RENDER start series={series} task={task_name} out={out_path}")
                frames = _render_video_frames(
                    nd2_path=str(cached_nd2_path),
                    frame_dir=frame_dir,
                    series=series,
                    size_t=size_t,
                    task_name=task_name,
                    cfg=cfg,
                    metadata_series=meta,
                    params=params,
                    log_file=log_file,
                )
                _append_runtime_log(log_file, f"VIDEO_RENDER frames={frames} series={series} task={task_name}")
                _encode_video_frames(frame_dir, out_path, int(cfg["fps"]), int(cfg["crf"]), log_file)
                try:
                    shutil.rmtree(frame_dir, ignore_errors=True)
                except Exception:
                    pass
                done_jobs += 1
                task.progress = int(round((done_jobs / total_jobs) * 100))
                db.commit()

        task.status = "SUCCEEDED"
        task.progress = 100
        if task_run:
            task_run.status = "SUCCEEDED"
        _append_runtime_log(log_file, "SUCCEEDED")
        db.commit()
        return {"status": "SUCCEEDED"}
    except Exception as e:
        canceled = "canceled" in str(e).lower()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "CANCELED" if canceled else "FAILED"
                task.last_error = None if canceled else str(e)[:4000]
            if task_run:
                task_run.status = "CANCELED" if canceled else "FAILED"
            db.commit()
        except Exception:
            pass
        _append_runtime_log(log_file, "CANCELED" if canceled else f"FAILED: {str(e)}")
        return {"status": "CANCELED" if canceled else "FAILED", "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass

def _archive_nd2_path(task_id: str, filename: str) -> str:
    return os.path.join(settings.ARCHIVE_ND2_DIR, str(task_id), filename)

def _cold_archive_status_path(run_dir: str) -> str:
    return os.path.join(run_dir, "cold_archive_nd2.json")

def _verify_file_size(src: str, dst: str) -> bool:
    try:
        return os.path.isfile(src) and os.path.isfile(dst) and os.path.getsize(src) == os.path.getsize(dst) and os.path.getsize(dst) > 0
    except Exception:
        return False

def _write_cold_archive_status(
    status_path: str,
    *,
    task_id: str,
    run_id: str,
    source_path: str,
    dest_path: str,
    state: str,
    message: str = "",
    bytes_total: Optional[int] = None,
    bytes_done: Optional[int] = None,
    verified: bool = False,
    error: Optional[str] = None,
    started_at: Optional[float] = None,
    completed_at: Optional[float] = None,
) -> dict[str, Any]:
    now = time.time()
    total = int(bytes_total or 0)
    done = int(bytes_done or 0)
    started = started_at or now
    percent = round(max(0.0, min(100.0, (float(done) / float(total)) * 100.0)), 2) if total > 0 else 0.0
    status = {
        "kind": "cold_archive",
        "task_id": task_id,
        "run_id": run_id,
        "source_path": source_path,
        "dest_path": dest_path,
        "state": state,
        "message": message,
        "bytes_total": total,
        "bytes_done": done,
        "percent": percent,
        "verified": bool(verified),
        "error": error,
        "started_at": started,
        "updated_at": now,
        "completed_at": completed_at,
    }
    _write_json_atomic(status_path, status)
    return status

def _start_nd2_cold_archive_transfer(
    *,
    task_id: str,
    run_id: str,
    hot_path: str,
    cold_path: str,
    run_dir: str,
    log_file: str,
) -> tuple[Optional[threading.Thread], dict[str, Any]]:
    status_path = _cold_archive_status_path(run_dir)
    try:
        total = int(os.path.getsize(hot_path) or 0)
    except Exception:
        total = 0

    if total <= 0:
        status = _write_cold_archive_status(
            status_path,
            task_id=task_id,
            run_id=run_id,
            source_path=hot_path,
            dest_path=cold_path,
            state="failed",
            message="Hot ND2 is missing or empty",
            error="Hot ND2 is missing or empty",
        )
        return None, {"status": status, "ok": False, "error": status["error"]}

    if _verify_file_size(hot_path, cold_path):
        status = _write_cold_archive_status(
            status_path,
            task_id=task_id,
            run_id=run_id,
            source_path=hot_path,
            dest_path=cold_path,
            state="completed",
            message="Cold archive already verified",
            bytes_total=total,
            bytes_done=total,
            verified=True,
            completed_at=time.time(),
        )
        return None, {"status": status, "ok": True, "verified": True}

    result: dict[str, Any] = {"ok": False, "verified": False, "error": None}
    started_at = time.time()
    _write_cold_archive_status(
        status_path,
        task_id=task_id,
        run_id=run_id,
        source_path=hot_path,
        dest_path=cold_path,
        state="queued",
        message="Waiting for cold archive transfer slot",
        bytes_total=total,
        bytes_done=0,
        started_at=started_at,
    )

    def _copy_worker() -> None:
        bytes_done = 0
        tmp = f"{cold_path}.tmp.{uuid.uuid4().hex}"
        try:
            with _cold_archive_transfer_semaphore:
                if _verify_file_size(hot_path, cold_path):
                    result["ok"] = True
                    result["verified"] = True
                    result["status"] = _write_cold_archive_status(
                        status_path,
                        task_id=task_id,
                        run_id=run_id,
                        source_path=hot_path,
                        dest_path=cold_path,
                        state="completed",
                        message="Cold archive already verified",
                        bytes_total=total,
                        bytes_done=total,
                        verified=True,
                        started_at=started_at,
                        completed_at=time.time(),
                    )
                    return

                os.makedirs(os.path.dirname(cold_path), exist_ok=True)
                _append_runtime_log(log_file, f"ND2 cold archive started. src={hot_path} dst={cold_path}")
                _write_cold_archive_status(
                    status_path,
                    task_id=task_id,
                    run_id=run_id,
                    source_path=hot_path,
                    dest_path=cold_path,
                    state="copying",
                    message="Copying ND2 to cold archive",
                    bytes_total=total,
                    bytes_done=0,
                    started_at=started_at,
                )
                last_write = 0.0
                with open(hot_path, "rb") as fsrc, open(tmp, "wb") as fdst:
                    for chunk in iter(lambda: fsrc.read(16 * 1024 * 1024), b""):
                        fdst.write(chunk)
                        bytes_done += len(chunk)
                        now = time.time()
                        if now - last_write >= 1.0:
                            _write_cold_archive_status(
                                status_path,
                                task_id=task_id,
                                run_id=run_id,
                                source_path=hot_path,
                                dest_path=cold_path,
                                state="copying",
                                message="Copying ND2 to cold archive",
                                bytes_total=total,
                                bytes_done=bytes_done,
                                started_at=started_at,
                            )
                            last_write = now
                os.replace(tmp, cold_path)
                verified = _verify_file_size(hot_path, cold_path)
                if not verified:
                    raise RuntimeError("Cold archive verification failed: size mismatch")
                result["ok"] = True
                result["verified"] = True
                result["status"] = _write_cold_archive_status(
                    status_path,
                    task_id=task_id,
                    run_id=run_id,
                    source_path=hot_path,
                    dest_path=cold_path,
                    state="completed",
                    message="Cold archive verified",
                    bytes_total=total,
                    bytes_done=total,
                    verified=True,
                    started_at=started_at,
                    completed_at=time.time(),
                )
                _append_runtime_log(log_file, f"ND2 cold archive verified. dst={cold_path}")
        except Exception as e:
            result["ok"] = False
            result["verified"] = False
            result["error"] = f"{type(e).__name__}: {str(e)}"
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            result["status"] = _write_cold_archive_status(
                status_path,
                task_id=task_id,
                run_id=run_id,
                source_path=hot_path,
                dest_path=cold_path,
                state="failed",
                message="Cold archive transfer failed",
                bytes_total=total,
                bytes_done=bytes_done,
                verified=False,
                error=result["error"],
                started_at=started_at,
                completed_at=time.time(),
            )
            _append_runtime_log(log_file, f"WARN: ND2 cold archive failed: {result['error']}")

    thread = threading.Thread(target=_copy_worker, daemon=True)
    thread.start()
    return thread, result

def _finish_nd2_cold_archive_transfer(
    *,
    transfer_thread: Optional[threading.Thread],
    transfer_result: Optional[dict[str, Any]],
    task: Task,
    hot_path: str,
    cold_path: str,
    db,
    log_file: str,
) -> bool:
    if transfer_thread is not None and transfer_thread.is_alive():
        _append_runtime_log(log_file, "Waiting for ND2 cold archive before hot cleanup")
        transfer_thread.join()

    verified = _verify_file_size(hot_path, cold_path)
    if verified:
        try:
            size = int(os.path.getsize(cold_path) or 0)
        except Exception:
            size = None
        task.nd2_local_path = cold_path
        task.nd2_local_bytes = size
        task.nd2_local_saved_at = datetime.utcnow()
        task.nd2_local_deleted_at = None
        db.add(task)
        db.commit()
        return True

    err = None
    if transfer_result:
        err = transfer_result.get("error")
    _append_runtime_log(log_file, f"WARN: Hot ND2 retained because cold archive is not verified. error={err or '-'}")
    return False

def _ensure_hot_nd2(
    *,
    task: Task,
    task_id: str,
    run_id: str,
    minio: MinioService,
    nd2_key: str,
    cached_nd2_path: str,
    images_dir: str,
    run_dir: str,
    db,
    log_file: str,
) -> str:
    cold_path = _archive_nd2_path(str(task_id), os.path.basename(cached_nd2_path))
    cold_exists = os.path.exists(cold_path) and os.path.getsize(cold_path) > 0 if os.path.exists(cold_path) else False
    hot_exists = os.path.exists(cached_nd2_path) and os.path.getsize(cached_nd2_path) > 0 if os.path.exists(cached_nd2_path) else False

    if cold_exists and (str(getattr(task, "nd2_local_path", "") or "") != cold_path or getattr(task, "nd2_local_deleted_at", None) is not None):
        try:
            size = int(os.path.getsize(cold_path) or 0)
        except Exception:
            size = None
        task.nd2_local_path = cold_path
        task.nd2_local_bytes = size
        if not getattr(task, "nd2_local_saved_at", None):
            task.nd2_local_saved_at = datetime.utcnow()
        task.nd2_local_deleted_at = None
        db.add(task)
        db.commit()

    if not hot_exists and cold_exists:
        _append_runtime_log(log_file, f"ND2: copying from archive to hot. src={cold_path} dst={cached_nd2_path}")
        _copy_file_atomic(cold_path, cached_nd2_path)
        hot_exists = os.path.exists(cached_nd2_path) and os.path.getsize(cached_nd2_path) > 0 if os.path.exists(cached_nd2_path) else False

    if not hot_exists:
        _download_nd2_with_progress(
            task_id=str(task_id),
            run_id=str(run_id),
            minio=minio,
            key=str(nd2_key),
            cached_nd2_path=cached_nd2_path,
            images_dir=images_dir,
            run_dir=run_dir,
            db=db,
            log_file=log_file,
        )
        hot_exists = os.path.exists(cached_nd2_path) and os.path.getsize(cached_nd2_path) > 0 if os.path.exists(cached_nd2_path) else False

    return cached_nd2_path

def _archive_run_dir(
    *,
    task_id: str,
    run_id: str,
    run_dir: str,
    task_run: Optional[TaskRun],
    db,
    log_file: str,
) -> str:
    dst = os.path.join(settings.ARCHIVE_RUNS_DIR, str(task_id), str(run_id))
    if os.path.abspath(run_dir) == os.path.abspath(dst):
        return run_dir
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            return dst
        shutil.move(run_dir, dst)
        if task_run:
            task_run.run_dir_archive = dst
            task_run.archived_at = datetime.utcnow()
            db.add(task_run)
            db.commit()
        return dst
    except Exception as e:
        _append_runtime_log(log_file, f"WARN: Failed to archive run_dir: {type(e).__name__}: {str(e)}")
        return run_dir

def _disk_usage_percent(path: str) -> float:
    total, used, _free = shutil.disk_usage(path)
    if total <= 0:
        return 0.0
    return (float(used) / float(total)) * 100.0

def _cleanup_cold_nd2_until_below_threshold(*, db, log_file: str) -> None:
    threshold = float(getattr(settings, "ARCHIVE_USAGE_THRESHOLD_PERCENT", 85) or 85)
    target = float(getattr(settings, "ARCHIVE_USAGE_TARGET_PERCENT", 85) or 85)
    base = str(settings.ARCHIVE_ND2_DIR)
    if not os.path.isdir(base):
        return
    while True:
        try:
            percent = _disk_usage_percent(base)
        except Exception:
            return
        if percent <= threshold:
            return
        task = (
            db.query(Task)
            .filter(Task.nd2_local_deleted_at.is_(None))
            .filter(Task.nd2_local_path.isnot(None))
            .order_by(Task.created_at.asc())
            .first()
        )
        if not task:
            return
        path = str(task.nd2_local_path or "")
        _append_runtime_log(log_file, f"ARCHIVE_CLEANUP nd2 percent={percent:.2f} removing task_id={task.id} path={path}")
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            _append_runtime_log(log_file, f"WARN: ARCHIVE_CLEANUP remove failed: {type(e).__name__}: {str(e)}")
        task.nd2_local_path = None
        task.nd2_local_deleted_at = datetime.utcnow()
        db.add(task)
        db.commit()
        if target < threshold:
            try:
                percent2 = _disk_usage_percent(base)
            except Exception:
                return
            if percent2 <= target:
                return

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
        cold_archive_thread: Optional[threading.Thread] = None
        cold_archive_result: Optional[dict[str, Any]] = None
        cold_nd2_path: Optional[str] = None
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
            cached_nd2_path = _ensure_hot_nd2(
                task=task,
                task_id=str(task_id),
                run_id=str(run_id),
                minio=minio,
                nd2_key=str(task.nd2_object_key),
                cached_nd2_path=cached_nd2_path,
                images_dir=images_dir,
                run_dir=run_dir,
                db=db,
                log_file=log_file,
            )

            cold_nd2_path = _archive_nd2_path(str(task_id), os.path.basename(str(cached_nd2_path)))
            cold_archive_thread, cold_archive_result = _start_nd2_cold_archive_transfer(
                task_id=str(task_id),
                run_id=str(run_id),
                hot_path=str(cached_nd2_path),
                cold_path=str(cold_nd2_path),
                run_dir=str(run_dir),
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

        matlab_bin = settings.MATLAB_BIN
        try:
             config_ver = db.query(AppConfig).filter(AppConfig.key == "system.matlab_version").first()
             if config_ver and config_ver.value:
                 if config_ver.value != "R2024a":
                     _append_runtime_log(
                         log_file,
                         f"Configuration loaded: system.matlab_version={config_ver.value}; forcing R2024a with BIN={matlab_bin}",
                     )
                 else:
                     _append_runtime_log(log_file, f"Configuration loaded: system.matlab_version=R2024a -> BIN={matlab_bin}")
             else:
                 _append_runtime_log(log_file, f"Configuration using default MATLAB_BIN={matlab_bin}")
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
                
            if mode == "debug":
                try:
                    _postprocess_debug_videos(run_dir=run_dir, log_file=log_file, max_px=720)
                except Exception as e:
                    _append_runtime_log(log_file, f"WARN: Debug video postprocess skipped: {type(e).__name__}: {str(e)}")

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
        cold_verified = False
        try:
            cold_path = cold_nd2_path or _archive_nd2_path(str(task_id), os.path.basename(str(cached_nd2_path)))
            cold_verified = _finish_nd2_cold_archive_transfer(
                transfer_thread=cold_archive_thread,
                transfer_result=cold_archive_result,
                task=task,
                hot_path=str(cached_nd2_path),
                cold_path=str(cold_path),
                db=db,
                log_file=log_file,
            )
        except Exception as e:
            _append_runtime_log(log_file, f"WARN: Failed to finalize ND2 cold archive: {type(e).__name__}: {str(e)}")

        run_dir = _archive_run_dir(
            task_id=str(task_id),
            run_id=str(run_id),
            run_dir=str(run_dir),
            task_run=task_run,
            db=db,
            log_file=log_file,
        )
        log_file = os.path.join(str(run_dir), "runtime.log")
        try:
            if cold_verified and os.path.exists(str(cached_nd2_path)):
                os.remove(str(cached_nd2_path))
        except Exception as e:
            _append_runtime_log(log_file, f"WARN: Failed to cleanup hot ND2: {type(e).__name__}: {str(e)}")
        _cleanup_cold_nd2_until_below_threshold(db=db, log_file=log_file)
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
