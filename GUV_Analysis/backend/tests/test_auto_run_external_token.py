import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import Task, User


def test_auto_run_with_external_token_creates_auto_exp_user(client: TestClient, db):
    db.query(Task).delete()
    db.query(User).delete()
    db.commit()

    settings.EXTERNAL_AUTORUN_TOKEN = "test-external-token"
    settings.EXTERNAL_AUTORUN_USERNAME = "auto-exp"

    fake_s3 = MagicMock()
    fake_s3.head_object.return_value = {"ContentLength": 123}
    fake_s3.put_object.return_value = {}

    run_id = uuid.uuid4()

    with patch("app.api.routes.tasks._create_s3_client", return_value=fake_s3), patch(
        "app.api.routes.tasks.QueueService.submit_task", return_value=run_id
    ):
        resp = client.post(
            "/api/tasks/auto-run",
            headers={"X-External-Token": "test-external-token"},
            json={
                "id": "ABCD_0001",
                "name": "Test Run 001",
                "filename": "sample.nd2",
                "run_mode": "final",
                "params": {"some_param": 123},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "ABCD_0001"
    assert data["run_id"] == str(run_id)
    assert data["status"] == "queued"

    user = db.query(User).filter(User.username == "auto-exp").first()
    assert user is not None

    task = db.query(Task).filter(Task.id == "ABCD_0001").first()
    assert task is not None
    assert task.user_id == user.id

