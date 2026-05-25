import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core import security
# Ensure Celery app is loaded so shared_task uses correct config
from app.worker.celery_app import celery_app
from app.api.routes import tasks, system, auth, users
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db.models import User

def _add_file_handler(logger: logging.Logger, filename: str, formatter: logging.Formatter, level: int) -> None:
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == filename:
            return
    handler = logging.FileHandler(filename)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _setup_logging() -> None:
    log_dir = os.path.join(settings.RUN_BASE_DIR, "system_logs")
    os.makedirs(log_dir, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    app_log = os.path.join(log_dir, "app.log")
    access_log = os.path.join(log_dir, "access.log")
    root_logger = logging.getLogger()
    if root_logger.level == logging.WARNING:
        root_logger.setLevel(logging.INFO)
    _add_file_handler(root_logger, app_log, formatter, logging.INFO)
    _add_file_handler(logging.getLogger("uvicorn.error"), app_log, formatter, logging.INFO)
    _add_file_handler(logging.getLogger("uvicorn.access"), access_log, formatter, logging.INFO)


_setup_logging()

# Create tables on startup (for simple dev setup)
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json")

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(tasks.router, prefix=f"{settings.API_V1_STR}/tasks", tags=["tasks"])
app.include_router(system.router, prefix=f"{settings.API_V1_STR}/system", tags=["system"])

@app.on_event("startup")
def create_initial_data():
    # Start system stats collection
    system.start_stats_collection()
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            user = User(
                username="admin",
                password_hash=security.get_password_hash("admin"),
                role="admin"
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "Welcome to GUV Analysis Platform API"}
