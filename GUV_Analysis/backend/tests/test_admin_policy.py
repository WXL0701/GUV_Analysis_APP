from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.api import deps
from app.core import security
from app.db.models import User, Task
from app.db.session import SessionLocal
import uuid
import sys

client = TestClient(app)

def run_test():
    db = SessionLocal()
    try:
        test_admin_permissions_and_password_policy(db)
    finally:
        db.close()

def test_admin_permissions_and_password_policy(db: Session):
    print("Starting Admin Policy Test...")
    # Cleanup potential leftover users from previous runs
    for uname in ["OtherUser", "SimpleUser", "SpecialUser", "ShortUser"]:
        u = db.query(User).filter(User.username == uname).first()
        if u:
            # Delete user's tasks first if any (cascade usually handles this but let's be safe)
            db.query(Task).filter(Task.user_id == u.id).delete()
            db.delete(u)
    db.commit()

    # 1. Setup Admin User
    admin_data = {"username": "Admin", "password": "12345678"}
    # Ensure admin exists (create_admin.py logic simulation)
    user = db.query(User).filter(User.username == "Admin").first()
    if not user:
        user = User(
            username="Admin",
            password_hash=security.get_password_hash("12345678"),
            role="admin",
        )
        db.add(user)
        db.commit()
    else:
        if user.role != "admin":
            user.role = "admin"
            db.commit()

    # 2. Login as Admin
    login_res = client.post("/api/auth/login", data=admin_data)
    assert login_res.status_code == 200, f"Admin login failed: {login_res.text}"
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. Test Admin Viewing All Tasks
    # First create a dummy task for another user
    other_user_data = {"username": "OtherUser", "password": "otherpassword123"}
    client.post("/api/auth/register", json=other_user_data)
    
    # Login as OtherUser
    other_login = client.post("/api/auth/login", data=other_user_data)
    other_token = other_login.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}
    
    # Create task as OtherUser
    task_id = "TestTask_" + str(uuid.uuid4())[:8]
    task_data = {"id": task_id, "name": "Test Task", "filename": "test.nd2", "size": 100}
    create_res = client.post("/api/tasks/", json=task_data, headers=other_headers)
    assert create_res.status_code == 200

    # Admin should see this task
    tasks_res = client.get("/api/tasks/", headers=admin_headers)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()["items"]
    # Check if task_id is in the list
    found = any(t["id"] == task_id for t in tasks)
    assert found, "Admin should see OtherUser's task"

    # 4. Test Password Policy - Registration
    # Valid simple password (letters + numbers, no case req)
    valid_user = {"username": "SimpleUser", "password": "lowercase1"}
    res = client.post("/api/auth/register", json=valid_user)
    if res.status_code != 200:
        print(f"Registration failed: {res.text}")
    assert res.status_code == 200, "Should allow lowercase + number"

    # Invalid special char
    invalid_user = {"username": "SpecialUser", "password": "password!"}
    res = client.post("/api/auth/register", json=invalid_user)
    assert res.status_code == 422, "Should fail due to special char" # Validation error

    # Invalid length
    short_user = {"username": "ShortUser", "password": "short1"}
    res = client.post("/api/auth/register", json=short_user)
    assert res.status_code == 422, "Should fail due to length"

    # 5. Test Password Policy - Update
    # Update OtherUser's password
    # Valid update
    update_valid = client.put("/api/users/me", json={"password": "newpass1"}, headers=other_headers)
    if update_valid.status_code != 200:
        print(f"Update failed: {update_valid.text}")
    assert update_valid.status_code == 200

    # Invalid update (special char)
    update_invalid = client.put("/api/users/me", json={"password": "newpass!"}, headers=other_headers)
    assert update_invalid.status_code == 422

    # 6. Test Permission Isolation (Regular user cannot see other's task)
    # Login as SimpleUser
    simple_login = client.post("/api/auth/login", data=valid_user)
    simple_token = simple_login.json()["access_token"]
    simple_headers = {"Authorization": f"Bearer {simple_token}"}
    
    # Try to access OtherUser's task
    res = client.get(f"/api/tasks/{task_id}", headers=simple_headers)
    assert res.status_code == 403, "Regular user should not access other user's task"

    # Try to list tasks - should not see OtherUser's task
    res = client.get("/api/tasks/", headers=simple_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    found = any(t["id"] == task_id for t in items)
    assert not found, "Regular user should not see other user's task in list"

    print("All tests passed!")

if __name__ == "__main__":
    run_test()
