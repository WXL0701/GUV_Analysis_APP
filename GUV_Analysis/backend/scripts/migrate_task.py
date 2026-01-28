import os
import shutil
import uuid
import datetime
import json
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Task, TaskRun, User
from app.core.config import settings

def migrate_task(old_uuid, new_id, new_name):
    db: Session = SessionLocal()
    
    # Paths
    old_path = os.path.join(settings.RUN_BASE_DIR, old_uuid)
    new_path = os.path.join(settings.RUN_BASE_DIR, new_id)
    
    # 1. Check if old folder exists
    if not os.path.exists(old_path):
        if os.path.exists(new_path):
            print(f"Old task folder not found, but target {new_path} exists. Proceeding with DB update.")
        else:
            print(f"Old task folder not found: {old_path}")
            return

    # 2. Check if new folder already exists
    if os.path.exists(new_path):
        print(f"Target folder already exists: {new_path}. Skipping rename.")
        # We assume if it exists, maybe we just need to populate DB
    else:
        # Rename folder
        print(f"Renaming {old_path} to {new_path}...")
        try:
            os.rename(old_path, new_path)
        except Exception as e:
            print(f"Error renaming folder: {e}")
            return

    # 3. Create or Update Task in DB
    task = db.query(Task).filter(Task.id == new_id).first()
    if not task:
        print(f"Creating new task record for {new_id} ({new_name})...")
        # Need a user ID. Find first user or create default?
        # Assuming database has at least one user or we can use a placeholder UUID if foreign key constraints allow?
        # Foreign Key constraint "users.id" exists.
        user = db.query(User).first()
        if not user:
            print("No users found in DB. Creating default user 'admin'.")
            user = User(username="admin", password_hash="hash")
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # Determine nd2 size if possible
        nd2_path = os.path.join(new_path, "images", "raw.nd2")
        size = 0
        if os.path.exists(nd2_path):
            size = os.path.getsize(nd2_path)
        
        task = Task(
            id=new_id,
            user_id=user.id,
            name=new_name,
            status="SUCCEEDED", # Assume succeeded for migrated history
            stage="STAGE_2_ANALYSIS",
            nd2_object_key=f"{new_id}/raw.nd2", # Virtual key
            nd2_size=size,
            params_version=0,
            created_at=datetime.datetime.now()
        )
        db.add(task)
        db.commit()
    else:
        print(f"Task record {new_id} already exists.")

    # 4. Scan for Runs and Create TaskRun records
    print(f"Scanning runs in {new_path}...")
    for item in os.listdir(new_path):
        run_path = os.path.join(new_path, item)
        if not os.path.isdir(run_path):
            continue
        if item == "images":
            continue
        
        try:
            run_id_uuid = uuid.UUID(item)
        except ValueError:
            print(f"Skipping non-UUID folder: {item}")
            continue
            
        # Check if run exists
        existing_run = db.query(TaskRun).filter(TaskRun.id == run_id_uuid).first()
        if existing_run:
            print(f"Run {item} already exists in DB.")
            continue
            
        print(f"Importing run {item}...")
        
        # Gather Metadata
        stat = os.stat(run_path)
        created_at = datetime.datetime.fromtimestamp(stat.st_ctime)
        
        params = {}
        params_file = os.path.join(run_path, "params.json")
        if os.path.exists(params_file):
            try:
                with open(params_file, 'r') as f:
                    params = json.load(f)
            except:
                pass
                
        # Determine Status/Mode
        mode = "final"
        status = "SUCCEEDED" # Default for history
        
        # Heuristics
        if params.get("Debug", {}).get("Enable") is True:
            mode = "debug"
        
        # Check files
        if os.path.exists(os.path.join(run_path, "output", "debug", "preview.mp4")):
            mode = "debug"
        
        new_run = TaskRun(
            id=run_id_uuid,
            task_id=new_id,
            run_mode=mode,
            status=status,
            created_at=created_at,
            params_snapshot=params
        )
        db.add(new_run)
        
    db.commit()
    print("Migration complete.")

if __name__ == "__main__":
    # Hardcoded based on user request and known context
    OLD_UUID = "bbe1c0e5-4cf8-4628-baa2-191d69428907"
    NEW_ID = "WXL_task001"
    NEW_NAME = "test006"
    
    migrate_task(OLD_UUID, NEW_ID, NEW_NAME)
