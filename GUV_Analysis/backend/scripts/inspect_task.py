import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.db.session import SessionLocal
from app.db.models import Task, User

def inspect_all_tasks():
    db = SessionLocal()
    try:
        tasks = db.query(Task).all()
        print(f"Total tasks: {len(tasks)}")
        for t in tasks:
            print(f"Task {t.id}: RunID={t.run_id_current} (Type: {type(t.run_id_current)})")
            # Check UUID validity
            if t.run_id_current:
                try:
                    import uuid
                    uuid.UUID(str(t.run_id_current))
                except ValueError:
                    print(f"  INVALID UUID: {t.run_id_current}")

    finally:
        db.close()

if __name__ == "__main__":
    inspect_all_tasks()
