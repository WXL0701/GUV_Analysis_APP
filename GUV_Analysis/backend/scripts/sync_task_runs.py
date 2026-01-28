import os
import uuid
import json
import datetime
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine
from app.db.models import Task, TaskRun, Base
from app.core.config import settings

def sync_task_runs():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        tasks_dir = settings.RUN_BASE_DIR
        if not os.path.exists(tasks_dir):
            print(f"Tasks directory not found: {tasks_dir}")
            return

        for task_id_str in os.listdir(tasks_dir):
            task_path = os.path.join(tasks_dir, task_id_str)
            if not os.path.isdir(task_path):
                continue
            
            try:
                task_id = uuid.UUID(task_id_str)
            except ValueError:
                continue

            # Check if task exists in DB
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                print(f"Task {task_id} not found in DB, skipping folder.")
                continue

            print(f"Scanning task {task_id}...")

            for run_id_str in os.listdir(task_path):
                run_path = os.path.join(task_path, run_id_str)
                if not os.path.isdir(run_path):
                    continue
                
                if run_id_str == "images":
                    continue

                try:
                    run_id = uuid.UUID(run_id_str)
                except ValueError:
                    continue

                # Check if run exists
                existing_run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
                if existing_run:
                    print(f"  Run {run_id} already exists.")
                    continue

                print(f"  Found orphan run {run_id}, analyzing...")
                
                # Gather Metadata
                # 1. Created At
                stat = os.stat(run_path)
                created_at = datetime.datetime.fromtimestamp(stat.st_ctime)
                
                # 2. Params
                params = {}
                params_path = os.path.join(run_path, "params.json")
                if os.path.exists(params_path):
                    try:
                        with open(params_path, 'r') as f:
                            params = json.load(f)
                    except:
                        pass
                
                # 3. Mode
                mode = "unknown"
                if params.get("Debug", {}).get("Enable") is True:
                    mode = "debug"
                elif params.get("Debug", {}).get("Enable") is False:
                    mode = "final"
                else:
                    # Guess from output folders
                    if os.path.exists(os.path.join(run_path, "output", "debug")):
                        mode = "debug"
                    elif os.path.exists(os.path.join(run_path, "output", "final")):
                        mode = "final"
                    # Guess from file structure (migrated folders)
                    elif os.path.exists(os.path.join(run_path, "results")):
                        mode = "final" # Likely final if results exist
                
                # 4. Status
                status = "FAILED"
                # Check for success indicators
                if mode == "final":
                    if os.path.exists(os.path.join(run_path, "output", "final", "result.csv")):
                        status = "SUCCEEDED"
                    elif os.path.exists(os.path.join(run_path, "results")): # Migrated folder
                         # Check if any .mat files exist in results
                         if any(f.endswith(".mat") for f in os.listdir(os.path.join(run_path, "results"))):
                             status = "SUCCEEDED"
                elif mode == "debug":
                     if os.path.exists(os.path.join(run_path, "output", "debug", "preview.mp4")):
                        status = "SUCCEEDED"
                
                # Fallback for migrated run
                if status == "FAILED" and os.path.exists(os.path.join(run_path, "results")):
                     status = "SUCCEEDED"

                print(f"  -> Creating Run: Mode={mode}, Status={status}, Date={created_at}")

                new_run = TaskRun(
                    id=run_id,
                    task_id=task_id,
                    run_mode=mode,
                    status=status,
                    created_at=created_at,
                    params_snapshot=params
                )
                db.add(new_run)
            
            db.commit()

    finally:
        db.close()

if __name__ == "__main__":
    sync_task_runs()
