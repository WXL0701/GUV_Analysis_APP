import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.base import Base
from app.db.session import engine
from app.db.models import Task, TaskRun, TaskArtifact, TaskEvent, User

def reset_db():
    print("Dropping all tables...")
    # Order matters for Foreign Keys, but drop_all handles it usually
    Base.metadata.drop_all(bind=engine)
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
