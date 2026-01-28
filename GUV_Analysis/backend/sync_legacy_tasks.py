import os
import sys
import uuid
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__)))

from app.core.config import settings
from app.db.base import Base
from app.db.models import User, Task, TaskRun

def get_db_session():
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def sync_tasks():
    db = get_db_session()
    
    # 1. Get Admin User
    admin = db.query(User).filter(User.username == "Admin").first()
    if not admin:
        print("Admin user not found! Please run create_admin.py first.")
        return
    
    tasks_dir = settings.RUN_BASE_DIR
    if not os.path.exists(tasks_dir):
        print(f"Tasks directory not found: {tasks_dir}")
        return
        
    print(f"Scanning {tasks_dir}...")
    
    # 2. Iterate Task Directories
    for task_id in os.listdir(tasks_dir):
        task_path = os.path.join(tasks_dir, task_id)
        if not os.path.isdir(task_path):
            continue
            
        print(f"Processing Task: {task_id}")
        
        # Check if task exists
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            print(f"  Creating new task record for {task_id}")
            task = Task(
                id=task_id,
                user_id=admin.id, # Assign to Admin by default
                name=task_id,
                status="UNKNOWN",
                stage="UNKNOWN",
                created_at=datetime.fromtimestamp(os.path.getctime(task_path))
            )
            db.add(task)
            db.commit()
            db.refresh(task)
        
        # 3. Scan for Runs
        runs = []
        for item in os.listdir(task_path):
            item_path = os.path.join(task_path, item)
            if os.path.isdir(item_path):
                # Check if it looks like a UUID
                try:
                    run_uuid = uuid.UUID(item)
                    runs.append((item, os.path.getmtime(item_path)))
                except ValueError:
                    continue
        
        # Sort runs by time (newest first)
        runs.sort(key=lambda x: x[1], reverse=True)
        
        for run_str, mtime in runs:
            run_uuid = uuid.UUID(run_str)
            # Check if run exists
            run = db.query(TaskRun).filter(TaskRun.id == run_uuid).first()
            if not run:
                print(f"  Creating run record: {run_str}")
                run = TaskRun(
                    id=run_uuid,
                    task_id=task.id,
                    run_mode="unknown",
                    status="COMPLETED", # Assume completed if folder exists
                    created_at=datetime.fromtimestamp(mtime)
                )
                db.add(run)
                db.commit()
        
        # Update Task status based on latest run
        if runs:
            latest_run_id = runs[0][0]
            try:
                task.run_id_current = uuid.UUID(latest_run_id)
            except ValueError:
                print(f"  Warning: Invalid UUID for run {latest_run_id}, skipping assignment.")
                task.run_id_current = None
            
            # Check for success markers in latest run
            latest_run_path = os.path.join(task_path, latest_run_id)
            if os.path.exists(os.path.join(latest_run_path, "AllXYResults.mat")):
                task.status = "SUCCEEDED"
            elif os.path.exists(os.path.join(latest_run_path, "cancel")):
                task.status = "CANCELED"
            else:
                task.status = "FAILED" # Or UNKNOWN
            
            db.commit()
            print(f"  Updated task status to {task.status} (Run: {latest_run_id})")

    db.close()
    print("Sync completed.")

if __name__ == "__main__":
    sync_tasks()
