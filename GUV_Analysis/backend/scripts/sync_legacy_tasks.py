import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add backend directory to sys.path to allow imports
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.db.session import SessionLocal
from app.db.models import Task, User
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sync_tasks():
    db = SessionLocal()
    try:
        # 1. Get Admin User
        admin = db.query(User).filter(User.username == "Admin").first()
        if not admin:
            logger.error("Admin user not found! Please run create_admin.py first.")
            return

        logger.info(f"Syncing tasks for Admin user: {admin.id}")

        # 2. Scan Directory
        tasks_dir = Path(settings.RUN_BASE_DIR)
        if not tasks_dir.exists():
            logger.error(f"Tasks directory not found: {tasks_dir}")
            return

        logger.info(f"Scanning directory: {tasks_dir}")

        count_new = 0
        count_existing = 0

        for entry in os.scandir(tasks_dir):
            if not entry.is_dir():
                continue
            
            task_id = entry.name
            
            # Check if exists in DB
            existing_task = db.query(Task).filter(Task.id == task_id).first()
            if existing_task:
                # Optional: specific logic if it exists but has no user
                if existing_task.user_id is None:
                    logger.info(f"Task {task_id} exists but has no user. Assigning to Admin.")
                    existing_task.user_id = admin.id
                    db.commit()
                else:
                    count_existing += 1
                continue

            # Create new task
            logger.info(f"Found orphaned task folder: {task_id}. Creating DB record...")
            
            task_dir = Path(entry.path)
            created_at = datetime.fromtimestamp(entry.stat().st_ctime)
            
            # Scan for ND2 file
            nd2_key = None
            nd2_size = None
            for f in task_dir.glob("*.nd2"):
                nd2_key = f"{task_id}/{f.name}"
                nd2_size = f.stat().st_size
                break # Just take the first one
            
            # Scan for Result CSV
            result_csv_key = None
            for f in task_dir.glob("*results.csv"):
                 result_csv_key = f"{task_id}/{f.name}"
                 break

            new_task = Task(
                id=task_id,
                user_id=admin.id,
                name=task_id,
                status="SUCCEEDED", # Assume legacy tasks are done/valid
                stage="STAGE_4_DONE", # Assuming done
                created_at=created_at,
                updated_at=datetime.utcnow(),
                nd2_object_key=nd2_key,
                nd2_size=nd2_size,
                result_csv_key=result_csv_key,
                progress=100
            )
            
            db.add(new_task)
            count_new += 1
        
        db.commit()
        logger.info(f"Sync completed. New tasks: {count_new}, Existing tasks: {count_existing}")

    except Exception as e:
        logger.error(f"Error during sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    sync_tasks()
