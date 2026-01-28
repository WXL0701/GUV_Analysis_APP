import sys
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Task, TaskRun
from app.core.config import settings

def check_params_sync():
    print(f"Connecting to database: {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    print("\n--- Checking Task Current Params (MinIO pointers) ---")
    tasks = db.query(Task).all()
    for task in tasks:
        print(f"Task: {task.id}")
        print(f"  Params Key: {task.params_object_key_current}")
        # We can't easily check MinIO content here without MinIO client setup, 
        # but we can check if the key looks valid.
        if not task.params_object_key_current:
            print("  [WARNING] No params key set. Using defaults?")
        
        # Check current run pointer
        print(f"  Current Run ID: {task.run_id_current}")

    print("\n--- Checking TaskRun Parameter Snapshots ---")
    runs = db.query(TaskRun).all()
    
    issues_found = 0
    
    for run in runs:
        status_tag = f"[{run.status}]"
        print(f"Run: {run.id} (Task: {run.task_id}) {status_tag}")
        
        snapshot = run.params_snapshot
        
        if snapshot is None:
            if run.status == "QUEUED" or run.status == "RUNNING":
                print("  [INFO] Snapshot pending (Run is active)")
            else:
                print("  [ERROR] Snapshot is NULL but run is finished/failed!")
                issues_found += 1
            continue
            
        if not isinstance(snapshot, dict):
            print(f"  [ERROR] Snapshot is not a dict: {type(snapshot)}")
            issues_found += 1
            continue
            
        # Check integrity of critical fields
        missing_keys = []
        critical_keys = ['PixelSize_um', 'FrameInterval_s', 'Read', 'Detect']
        for k in critical_keys:
            if k not in snapshot:
                missing_keys.append(k)
        
        if missing_keys:
            print(f"  [WARNING] Missing keys in snapshot: {missing_keys}")
            # This might be an old version, not necessarily an error, but a sync issue for UI
            
        # Check nested integrity
        if 'Detect' in snapshot:
            if 'Opts' not in snapshot['Detect']:
                 print("  [WARNING] Detect.Opts missing")
            elif 'bin' not in snapshot['Detect'].get('Opts', {}):
                 print("  [WARNING] Detect.Opts.bin missing")

    print(f"\n--- Analysis Complete. Issues found: {issues_found} ---")
    
if __name__ == "__main__":
    check_params_sync()
