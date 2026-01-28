import sys
import os

# Add backend directory to sys.path so we can import app
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.db.session import engine

def migrate():
    with engine.connect() as conn:
        print("Migrating database...")
        try:
            # Check if columns exist before adding (Postgres supports IF NOT EXISTS for ADD COLUMN in newer versions, 
            # but standard SQL often requires separate checks or 'ADD COLUMN IF NOT EXISTS' which Postgres 9.6+ supports)
            # Assuming Postgres 9.6+
            
            conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS dependencies JSONB DEFAULT '[]'"))
            conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0"))
            
            conn.commit()
            print("Migration successful.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
