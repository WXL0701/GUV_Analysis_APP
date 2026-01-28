from fastapi.testclient import TestClient
from app.db.models import Task

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
