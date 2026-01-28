from app.db.session import SessionLocal
from app.db.models import User
from app.core import security
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_admin_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "Admin").first()
        if user:
            logger.info("Admin user already exists.")
            # Ensure role is admin
            if user.role != "admin":
                user.role = "admin"
                db.commit()
                logger.info("Updated Admin user role to 'admin'.")
            return

        logger.info("Creating Admin user...")
        user = User(
            username="Admin",
            password_hash=security.get_password_hash("12345678"),
            role="admin",
        )
        db.add(user)
        db.commit()
        logger.info("Admin user created successfully.")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
