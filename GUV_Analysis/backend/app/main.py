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
