import json
from typing import Optional, List, Tuple

from app.worker.tasks import _maybe_cleanup_remote_nd2_after_success


class _FakeStat:
    def __init__(self, *, size: int, etag: str):
        self.size = size
        self.etag = etag


class _FakeClient:
    def __init__(self, *, stat: Optional[_FakeStat] = None, stat_exc: Optional[Exception] = None, remove_exc: Optional[Exception] = None):
        self._stat = stat
        self._stat_exc = stat_exc
        self._remove_exc = remove_exc
        self.removed: List[Tuple[str, str]] = []

    def stat_object(self, bucket: str, key: str):
        if self._stat_exc is not None:
            raise self._stat_exc
        if self._stat is None:
            raise RuntimeError("NoSuchKey")
        return self._stat

    def remove_object(self, bucket: str, key: str):
        if self._remove_exc is not None:
            raise self._remove_exc
        self.removed.append((bucket, key))


class _FakeMinio:
    def __init__(self, *, bucket: str, client: _FakeClient):
        self.bucket = bucket
        self.client = client


def test_cleanup_deletes_remote_when_valid(tmp_path):
    task_id = "t1"
    nd2_key = f"tasks/{task_id}/a.nd2"
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)

    cached = images_dir / "a.nd2"
    cached.write_bytes(b"x" * 16)

    (images_dir / "nd2.meta.json").write_text(
        json.dumps({"remote_key": nd2_key, "bytes_total": 16, "etag": "e1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    fake_client = _FakeClient(stat=_FakeStat(size=16, etag="e1"))
    minio = _FakeMinio(bucket="b", client=fake_client)
    log_file = str(tmp_path / "runtime.log")

    _maybe_cleanup_remote_nd2_after_success(
        task_id=task_id,
        minio=minio,
        nd2_key=nd2_key,
        cached_nd2_path=str(cached),
        images_dir=str(images_dir),
        log_file=log_file,
    )

    assert fake_client.removed == [("b", nd2_key)]
    assert (images_dir / "nd2.remote_deleted.json").exists()


def test_cleanup_skips_when_size_mismatch(tmp_path):
    task_id = "t2"
    nd2_key = f"tasks/{task_id}/a.nd2"
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)

    cached = images_dir / "a.nd2"
    cached.write_bytes(b"x" * 16)

    (images_dir / "nd2.meta.json").write_text(
        json.dumps({"remote_key": nd2_key, "bytes_total": 16, "etag": "e1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    fake_client = _FakeClient(stat=_FakeStat(size=32, etag="e1"))
    minio = _FakeMinio(bucket="b", client=fake_client)
    log_file = str(tmp_path / "runtime.log")

    _maybe_cleanup_remote_nd2_after_success(
        task_id=task_id,
        minio=minio,
        nd2_key=nd2_key,
        cached_nd2_path=str(cached),
        images_dir=str(images_dir),
        log_file=log_file,
    )

    assert fake_client.removed == []
    assert not (images_dir / "nd2.remote_deleted.json").exists()


def test_cleanup_skips_when_etag_mismatch(tmp_path):
    task_id = "t3"
    nd2_key = f"tasks/{task_id}/a.nd2"
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)

    cached = images_dir / "a.nd2"
    cached.write_bytes(b"x" * 16)

    (images_dir / "nd2.meta.json").write_text(
        json.dumps({"remote_key": nd2_key, "bytes_total": 16, "etag": "e1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    fake_client = _FakeClient(stat=_FakeStat(size=16, etag="e2"))
    minio = _FakeMinio(bucket="b", client=fake_client)
    log_file = str(tmp_path / "runtime.log")

    _maybe_cleanup_remote_nd2_after_success(
        task_id=task_id,
        minio=minio,
        nd2_key=nd2_key,
        cached_nd2_path=str(cached),
        images_dir=str(images_dir),
        log_file=log_file,
    )

    assert fake_client.removed == []
    assert not (images_dir / "nd2.remote_deleted.json").exists()
