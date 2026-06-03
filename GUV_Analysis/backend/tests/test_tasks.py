from fastapi.testclient import TestClient
import io
import os
import subprocess
import uuid
import zipfile

from app.core.config import settings
from app.db.models import Task, TaskRun

def test_read_tasks_empty(client: TestClient, db):
    # Ensure DB is empty
    db.query(Task).delete()
    db.commit()

    response = client.get("/api/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 0

def test_get_stats_empty(client: TestClient, db):
    # Ensure DB is empty
    db.query(Task).delete()
    db.commit()

    response = client.get("/api/tasks/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["queued"] == 0

def test_create_task_and_stats(client: TestClient, db):
    # Manually create a task in DB since we might not have a create endpoint exposed or we want to test stats directly
    # Note: The app might use Celery to create tasks, but we can insert into DB directly for testing stats
    task = Task(
        id="test-task-1",
        name="Test Task",
        status="QUEUED",
        priority=50
    )
    db.add(task)
    db.commit()

    response = client.get("/api/tasks/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["queued"] == 1
    assert data["running"] == 0

def test_task_filtering(client: TestClient, db):
    # Clear DB
    db.query(Task).delete()
    
    t1 = Task(id="t1", name="Active", status="RUNNING", priority=10)
    t2 = Task(id="t2", name="Queued", status="QUEUED", priority=10)
    t3 = Task(id="t3", name="History", status="SUCCEEDED", priority=10)
    
    db.add_all([t1, t2, t3])
    db.commit()

    # Test active filter
    res_active = client.get("/api/tasks/?filter_type=active")
    assert res_active.status_code == 200
    data = res_active.json()
    assert data["total"] == 2 # RUNNING + QUEUED

    # Test history filter
    res_history = client.get("/api/tasks/?filter_type=history")
    assert res_history.status_code == 200
    data = res_history.json()
    assert data["total"] == 1 # SUCCEEDED

def test_artifact_list_returns_video_metadata(client: TestClient, db, tmp_path, monkeypatch):
    db.query(TaskRun).delete()
    db.query(Task).delete()
    db.commit()

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(settings, "ARCHIVE_RUNS_DIR", str(tmp_path / "archive" / "runs"))

    task_id = "artifact-meta-task"
    run_id = uuid.uuid4()
    run_dir = tmp_path / "runs" / task_id / str(run_id)
    debug_dir = run_dir / "output" / "debug"
    debug_dir.mkdir(parents=True)
    (debug_dir / "preview.mp4").write_bytes(b"mp4")
    (debug_dir / "preview.avi").write_bytes(b"avi")

    task = Task(id=task_id, name="Artifact Meta", status="SUCCEEDED", run_id_current=run_id)
    run = TaskRun(id=run_id, task_id=task_id, run_mode="debug", status="SUCCEEDED")
    db.add_all([task, run])
    db.commit()

    response = client.get(f"/api/tasks/{task_id}/artifacts/list", params={"run_id": str(run_id)})
    assert response.status_code == 200
    videos = response.json()["videos"]
    assert videos[0]["name"] == "preview.mp4"
    assert videos[0]["mime"] == "video/mp4"
    assert videos[0]["playable"] is True
    avi = next(v for v in videos if v["name"] == "preview.avi")
    assert avi["mime"] == "video/x-msvideo"
    assert avi["playable"] is False

def test_artifact_list_returns_video_mode_artifacts(client: TestClient, db, tmp_path, monkeypatch):
    db.query(TaskRun).delete()
    db.query(Task).delete()
    db.commit()

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(settings, "ARCHIVE_RUNS_DIR", str(tmp_path / "archive" / "runs"))

    task_id = "video-artifact-task"
    run_id = uuid.uuid4()
    video_dir = tmp_path / "runs" / task_id / str(run_id) / "output" / "video"
    video_dir.mkdir(parents=True)
    (video_dir / "XY001_MERGE.mp4").write_bytes(b"mp4")
    (video_dir / "XY001_C01.mp4").write_bytes(b"mp4")

    task = Task(id=task_id, name="Video Artifact", status="SUCCEEDED", run_id_current=run_id)
    run = TaskRun(id=run_id, task_id=task_id, run_mode="video", status="SUCCEEDED")
    db.add_all([task, run])
    db.commit()

    response = client.get(f"/api/tasks/{task_id}/artifacts/list", params={"run_id": str(run_id)})
    assert response.status_code == 200
    videos = response.json()["videos"]
    merge = next(v for v in videos if v["name"] == "XY001_MERGE.mp4")
    c01 = next(v for v in videos if v["name"] == "XY001_C01.mp4")
    assert merge["mode"] == "merge"
    assert merge["playable"] is True
    assert c01["channel"] == "C01"

def test_artifact_archive_excludes_large_raw_files(client: TestClient, db, tmp_path, monkeypatch):
    db.query(TaskRun).delete()
    db.query(Task).delete()
    db.commit()

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(settings, "ARCHIVE_RUNS_DIR", str(tmp_path / "archive" / "runs"))

    task_id = "archive-task"
    run_id = uuid.uuid4()
    run_dir = tmp_path / "runs" / task_id / str(run_id)
    (run_dir / "output" / "final").mkdir(parents=True)
    (run_dir / "output" / "debug").mkdir(parents=True)
    (run_dir / "output" / "video").mkdir(parents=True)
    (run_dir / "TrackDiag").mkdir(parents=True)
    (run_dir / "runtime.log").write_text("runtime", encoding="utf-8")
    (run_dir / "params.json").write_text("{}", encoding="utf-8")
    (run_dir / "cold_archive_nd2.json").write_text("{}", encoding="utf-8")
    (run_dir / "output" / "final" / "AllXYResults.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (run_dir / "output" / "debug" / "preview.mp4").write_bytes(b"mp4")
    (run_dir / "output" / "video" / "XY001_MERGE.mp4").write_bytes(b"mp4")
    (run_dir / "video.params.json").write_text("{}", encoding="utf-8")
    (run_dir / "TrackDiag" / "diag.json").write_text("{}", encoding="utf-8")
    (run_dir / "raw.nd2").write_bytes(b"raw")
    (run_dir / "output" / "final" / "FrameStore.h5").write_bytes(b"h5")
    (run_dir / "output" / "final" / "tracks.mat").write_bytes(b"mat")

    task = Task(id=task_id, name="Archive", status="SUCCEEDED", run_id_current=run_id)
    run = TaskRun(id=run_id, task_id=task_id, run_mode="final", status="SUCCEEDED")
    db.add_all([task, run])
    db.commit()

    response = client.get(f"/api/tasks/{task_id}/artifacts/archive", params={"run_id": str(run_id)})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
    assert "runtime.log" in names
    assert "params.json" in names
    assert "cold_archive_nd2.json" in names
    assert "output/final/AllXYResults.csv" in names
    assert "output/debug/preview.mp4" in names
    assert "output/video/XY001_MERGE.mp4" in names
    assert "video.params.json" in names
    assert "TrackDiag/diag.json" in names
    assert "raw.nd2" not in names
    assert "output/final/FrameStore.h5" not in names
    assert "output/final/tracks.mat" not in names

def test_video_run_endpoint_submits_video_mode(client: TestClient, db, tmp_path, monkeypatch):
    from app.api.routes import tasks as task_routes

    db.query(TaskRun).delete()
    db.query(Task).delete()
    db.commit()

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    task_id = "video-run-task"
    cache_dir = tmp_path / "runs" / task_id
    cache_dir.mkdir(parents=True)
    (cache_dir / "params.latest.json").write_text('{"Video":{"Tasks":["Merge"]}}', encoding="utf-8")
    task = Task(id=task_id, name="Video Run", status="READY")
    db.add(task)
    db.commit()

    calls = []

    def fake_submit(db_arg, task_arg, mode, params_snapshot=None):
        calls.append((task_arg.id, mode, params_snapshot))
        return "run-video-1"

    monkeypatch.setattr(task_routes.QueueService, "submit_task", fake_submit)

    response = client.post(f"/api/tasks/{task_id}/video/run")
    assert response.status_code == 200
    assert response.json()["run_id"] == "run-video-1"
    assert calls == [(task_id, "video", {"Video": {"Tasks": ["Merge"]}})]

def test_debug_video_postprocess_scans_avi_and_targets_mp4(tmp_path, monkeypatch):
    from app.worker import tasks as worker_tasks

    run_dir = tmp_path / "run"
    debug_dir = run_dir / "output" / "debug"
    nested_dir = debug_dir / "nested"
    nested_dir.mkdir(parents=True)
    (debug_dir / "preview.avi").write_bytes(b"avi")
    (nested_dir / "refC01.avi").write_bytes(b"avi")
    (debug_dir / "ignore.mp4").write_bytes(b"mp4")
    log_file = run_dir / "runtime.log"

    calls = []

    def fake_transcode(src_path, dst_path, log_file_arg, max_px=720):
        calls.append((src_path, dst_path, log_file_arg, max_px))
        return True

    monkeypatch.setattr(worker_tasks, "_transcode_debug_video_to_mp4", fake_transcode)

    result = worker_tasks._postprocess_debug_videos(str(run_dir), str(log_file), max_px=720)

    assert result == {"found": 2, "converted": 2}
    targets = {os.path.relpath(call[1], run_dir) for call in calls}
    assert targets == {"output/debug/preview.mp4", "output/debug/nested/refC01.mp4"}
    assert all(call[3] == 720 for call in calls)

def test_debug_video_transcode_uses_browser_compatible_low_res_mp4(tmp_path, monkeypatch):
    from app.worker import tasks as worker_tasks

    src = tmp_path / "preview.avi"
    dst = tmp_path / "preview.mp4"
    log_file = tmp_path / "runtime.log"
    src.write_bytes(b"avi")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/matlab/lib")
    monkeypatch.setenv("LD_PRELOAD", "/matlab/preload.so")
    monkeypatch.setattr(worker_tasks, "_find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    captured = {}

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(cmd, stdout, stderr, text, timeout, env):
        captured["cmd"] = cmd
        captured["env"] = env
        tmp_out = cmd[-1]
        with open(tmp_out, "wb") as f:
            f.write(b"mp4")
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert worker_tasks._transcode_debug_video_to_mp4(str(src), str(dst), str(log_file), max_px=720) is True
    assert dst.read_bytes() == b"mp4"
    cmd = captured["cmd"]
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-pix_fmt" in cmd and cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "-preset" in cmd and cmd[cmd.index("-preset") + 1] == "veryfast"
    assert "-crf" in cmd and cmd[cmd.index("-crf") + 1] == "28"
    assert "-movflags" in cmd and cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert "min(720,iw)" in cmd[cmd.index("-vf") + 1]
    assert "LD_LIBRARY_PATH" not in captured["env"]
    assert "LD_PRELOAD" not in captured["env"]

def test_nd2_preview_resolves_cold_archive_when_hot_missing(client: TestClient, db, tmp_path, monkeypatch):
    from app.api.routes import tasks as task_routes

    db.query(TaskRun).delete()
    db.query(Task).delete()
    db.commit()

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(settings, "ARCHIVE_ND2_DIR", str(tmp_path / "archive" / "nd2"))

    task_id = "nd2-cold-preview"
    cold_dir = tmp_path / "archive" / "nd2" / task_id
    cold_dir.mkdir(parents=True)
    cold_nd2 = cold_dir / "sample.nd2"
    cold_nd2.write_bytes(b"nd2")

    task = Task(id=task_id, name="ND2 Preview", status="SUCCEEDED", nd2_object_key="uploads/sample.nd2")
    db.add(task)
    db.commit()

    assert task_routes._resolve_task_nd2_path(task) == str(cold_nd2)

def test_nd2_preview_environment_reports_missing_matlab(monkeypatch, tmp_path):
    from app.api.routes import tasks as task_routes
    from fastapi import HTTPException

    nd2_path = tmp_path / "sample.nd2"
    nd2_path.write_bytes(b"nd2")
    bf_root = tmp_path / "bfmatlab"
    bf_root.mkdir()

    monkeypatch.setattr(settings, "MATLAB_BIN", str(tmp_path / "missing_matlab"))
    monkeypatch.setattr(settings, "BFMATLAB_ROOT", str(bf_root))

    try:
        task_routes._validate_nd2_preview_environment(str(nd2_path))
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "MATLAB executable is not available" in exc.detail
    else:
        raise AssertionError("Expected HTTPException for missing MATLAB")

def test_nd2_preview_helper_accepts_output_written_before_timeout(monkeypatch, tmp_path):
    from app.api.routes import tasks as task_routes

    nd2_path = tmp_path / "sample.nd2"
    nd2_path.write_bytes(b"nd2")
    out_path = tmp_path / "metadata.json"
    out_path.write_text('{"series":[]}', encoding="utf-8")
    bf_root = tmp_path / "bfmatlab"
    bf_root.mkdir()
    matlab_bin = tmp_path / "matlab"
    matlab_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(settings, "MATLAB_BIN", str(matlab_bin))
    monkeypatch.setattr(settings, "BFMATLAB_ROOT", str(bf_root))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("matlab", 1)))

    task_routes._run_nd2_preview_helper(mode="metadata", nd2_path=str(nd2_path), out_path=str(out_path))

def test_nd2_preview_cache_path_splits_quality_and_source_stamp(monkeypatch, tmp_path):
    from app.api.routes import tasks as task_routes

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    nd2_path = tmp_path / "sample.nd2"
    nd2_path.write_bytes(b"nd2")

    fast_path = task_routes._nd2_preview_cache_path(
        task_id="task-a",
        nd2_path=str(nd2_path),
        quality="fast",
        max_px=1024,
        series=0,
        z=0,
        c=0,
        c2=1,
        t=0,
        mode="merge",
        lut="green",
        lut2="red",
        min_value="auto",
        max_value="auto",
    )
    full_path = task_routes._nd2_preview_cache_path(
        task_id="task-a",
        nd2_path=str(nd2_path),
        quality="full",
        max_px=1024,
        series=0,
        z=0,
        c=0,
        c2=1,
        t=0,
        mode="merge",
        lut="green",
        lut2="red",
        min_value="auto",
        max_value="auto",
    )

    assert "/nd2_preview_cache/fast/" in fast_path
    assert "/nd2_preview_cache/full/" in full_path
    assert fast_path != full_path
    assert "mtime" in fast_path and "size" in fast_path

def test_nd2_preview_cache_key_distinguishes_max_px(monkeypatch, tmp_path):
    from app.api.routes import tasks as task_routes

    monkeypatch.setattr(settings, "RUN_BASE_DIR", str(tmp_path / "runs"))
    nd2_path = tmp_path / "sample.nd2"
    nd2_path.write_bytes(b"nd2")

    path_768 = task_routes._nd2_preview_cache_path(
        task_id="task-a",
        nd2_path=str(nd2_path),
        quality="fast",
        max_px=768,
        series=0,
        z=0,
        c=0,
        c2=1,
        t=0,
        mode="single",
        lut="gray",
        lut2="red",
        min_value="auto",
        max_value="auto",
    )
    path_1024 = task_routes._nd2_preview_cache_path(
        task_id="task-a",
        nd2_path=str(nd2_path),
        quality="fast",
        max_px=1024,
        series=0,
        z=0,
        c=0,
        c2=1,
        t=0,
        mode="single",
        lut="gray",
        lut2="red",
        min_value="auto",
        max_value="auto",
    )

    assert path_768 != path_1024

def test_nd2_prefetch_skips_when_semaphore_busy(monkeypatch, tmp_path):
    from app.api.routes import tasks as task_routes

    nd2_path = tmp_path / "sample.nd2"
    nd2_path.write_bytes(b"nd2")
    acquired = task_routes._nd2_preview_prefetch_semaphore.acquire(blocking=False)
    assert acquired is True
    try:
        calls = []
        monkeypatch.setattr(task_routes, "_run_java_nd2_preview_helper", lambda **kwargs: calls.append(kwargs))
        task_routes._prefetch_nd2_fast_previews(
            task_id="task-a",
            nd2_path=str(nd2_path),
            series_values=[0],
            max_px=1024,
        )
        assert calls == []
    finally:
        task_routes._nd2_preview_prefetch_semaphore.release()
