import uuid
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.db.models import Task, TaskRun, User
from app.services.queue_service import QueueService

def test_queue_submission(db: Session):
    """
    Test that submitting a task:
    1. Creates a TaskRun with status QUEUED
    2. Updates Task status to QUEUED
    3. Calls Celery delay()
    """
    # Create a dummy user and task
    user = User(id=uuid.uuid4(), username="queue_tester", password_hash="pw", role="user")
    db.add(user)
    db.commit()

    task_id = str(uuid.uuid4())
    task = Task(id=task_id, user_id=user.id, name="Test Queue Task", status="READY")
    db.add(task)
    db.commit()

    # Mock Celery
    with patch("app.services.queue_service.run_analysis_task.delay") as mock_delay:
        run_id = QueueService.submit_task(db, task, "debug", {"param": 1})
        
        # Verify DB State
        assert task.status == "QUEUED"
        assert str(task.run_id_current) == run_id
        
        run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
        assert run is not None
        assert run.status == "QUEUED"
        assert run.run_mode == "debug"
        assert run.params_snapshot == {"param": 1}
        
        # Verify Celery Call
        mock_delay.assert_called_once_with(task_id, "debug", run_id)

def test_queue_submission_video_dispatches_video_task(db: Session):
    user = User(id=uuid.uuid4(), username="video_queue_tester", password_hash="pw", role="user")
    db.add(user)
    db.commit()

    task_id = str(uuid.uuid4())
    task = Task(id=task_id, user_id=user.id, name="Video Queue Task", status="READY")
    db.add(task)
    db.commit()

    with patch("app.services.queue_service.run_analysis_task.delay") as analysis_delay, \
         patch("app.services.queue_service.run_video_task.delay") as video_delay:
        run_id = QueueService.submit_task(db, task, "video", {"Video": {"Tasks": ["Merge"]}})

        run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
        assert run is not None
        assert run.run_mode == "video"
        assert run.params_snapshot == {"Video": {"Tasks": ["Merge"]}}
        analysis_delay.assert_not_called()
        video_delay.assert_called_once_with(task_id, run_id)

def test_queue_status_monitoring(db: Session):
    """
    Test that queue status counts are correct.
    """
    # Clear existing tasks (or just count what we add)
    initial_status = QueueService.get_queue_status(db)
    
    # Create user for FK
    user = User(id=uuid.uuid4(), username="status_tester", password_hash="pw", role="user")
    db.add(user)
    db.commit()
    
    # Add a QUEUED task
    t1 = Task(id=str(uuid.uuid4()), user_id=user.id, name="Q1", status="QUEUED")
    db.add(t1)
    
    # Add a RUNNING task
    t2 = Task(id=str(uuid.uuid4()), user_id=user.id, name="R1", status="RUNNING_DEBUG")
    db.add(t2)
    
    # Add a COMPLETED task
    t3 = Task(id=str(uuid.uuid4()), user_id=user.id, name="C1", status="SUCCEEDED")
    db.add(t3)
    
    db.commit()
    
    new_status = QueueService.get_queue_status(db)
    
    assert new_status["queued"] == initial_status["queued"] + 1
    assert new_status["running"] == initial_status["running"] + 1
    assert new_status["total_active"] == new_status["queued"] + new_status["running"]

def test_queue_api_endpoint(client):
    """
    Test the GET /api/tasks/queue/status endpoint
    """
    # Note: client fixture overrides authentication
    response = client.get("/api/tasks/queue/status")
    assert response.status_code == 200
    data = response.json()
    assert "queued" in data
    assert "running" in data
    assert "total_active" in data
