import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, BigInteger, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)
# Relationships
    tasks = relationship("Task", back_populates="owner")
    # sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    # received_messages = relationship("Message", foreign_keys="Message.receiver_id", back_populates="receiver")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(32), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    name = Column(String)
    status = Column(String, default="DRAFT")  # DRAFT, UPLOADING, READY, QUEUED, RUNNING_DEBUG, RUNNING_FINAL, SUCCEEDED, FAILED, CANCELED
    stage = Column(String, default="STAGE_1_UPLOAD")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    nd2_object_key = Column(String)
    nd2_size = Column(BigInteger)
    params_object_key_current = Column(String)
    params_version = Column(Integer, default=0)
    debug_mode = Column(Boolean, default=True)
    cancel_requested = Column(Boolean, default=False)
    last_error = Column(String)
    run_id_current = Column(UUID(as_uuid=True))
    result_csv_key = Column(String)
    last_preview_key = Column(String)
    
    # Task Queue fields
    priority = Column(Integer, default=0)
    dependencies = Column(JSONB, default=[])
    progress = Column(Integer, default=0)

    owner = relationship("User", back_populates="tasks")
    artifacts = relationship("TaskArtifact", back_populates="task")
    events = relationship("TaskEvent", back_populates="task")
    runs = relationship("TaskRun", back_populates="task")

class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(32), ForeignKey("tasks.id"))
    run_mode = Column(String) # debug, final
    status = Column(String, default="QUEUED") # QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELED
    params_snapshot = Column(JSONB) # Snapshot of parameters for this run
    started_at = Column(DateTime, nullable=True) # Actual start time
    created_at = Column(DateTime, default=datetime.utcnow)
    task = relationship("Task", back_populates="runs")

class TaskArtifact(Base):
    __tablename__ = "task_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(32), ForeignKey("tasks.id"))
    kind = Column(String)  # raw, params, preview, csv, log
    object_key = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    meta = Column(JSONB)

    task = relationship("Task", back_populates="artifacts")

class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(32), ForeignKey("tasks.id"))
    ts = Column(DateTime, default=datetime.utcnow)
    level = Column(String) # info, warn, error
    message = Column(String)

    task = relationship("Task", back_populates="events")

class SystemStat(Base):
    __tablename__ = "system_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    disk_percent = Column(Float)
    net_sent = Column(BigInteger)
    net_recv = Column(BigInteger)

class AppConfig(Base):
    __tablename__ = "app_configs"

    key = Column(String, primary_key=True)
    value = Column(String)
    description = Column(String)
