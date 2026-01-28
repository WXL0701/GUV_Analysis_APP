from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
import uuid
from datetime import datetime, timezone
import re

def _encode_datetime_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")

class APIModel(BaseModel):
    class Config:
        json_encoders = {datetime: _encode_datetime_utc}

class TaskCreate(BaseModel):
    id: str
    name: str
    filename: str
    size: int

    @validator('id')
    def validate_id(cls, v):
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,31}$', v):
            raise ValueError('任务ID格式错误，请使用字母开头，4-32位字母数字下划线组合')
        return v

class TaskCreateResponse(BaseModel):
    task_id: str
    uid: str
    nd2_object_key: str
    presigned_put_url: str

class TaskAutoRunRequest(BaseModel):
    id: str
    name: str
    filename: str
    params: Dict[str, Any] = Field(default_factory=dict)
    run_mode: str = "final"
    size: Optional[int] = None

    @validator('id')
    def validate_id(cls, v):
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,31}$', v):
            raise ValueError('任务ID格式错误，请使用字母开头，4-32位字母数字下划线组合')
        return v

    @validator('run_mode')
    def validate_run_mode(cls, v):
        if v not in ("final", "debug"):
            raise ValueError('run_mode 必须为 "final" 或 "debug"')
        return v

class TaskAutoRunResponse(BaseModel):
    task_id: str
    run_id: str
    nd2_object_key: str
    params_key: str
    status: str

class TaskUpdateParams(BaseModel):
    params: Dict[str, Any]

class TaskQueueUpdate(BaseModel):
    priority: Optional[int] = None
    dependencies: Optional[List[str]] = None

class TaskOut(APIModel):
    id: str
    name: str
    status: str
    stage: str
    created_at: datetime
    last_error: Optional[str] = None
    debug_mode: bool = False
    run_id_current: Optional[uuid.UUID] = None
    nd2_object_key: Optional[str] = None
    owner_name: Optional[str] = None
    queue_position: Optional[int] = None
    
    # Task Queue fields
    priority: int = 0
    dependencies: List[str] = []
    progress: int = 0

    class Config(APIModel.Config):
        from_attributes = True

class AppConfigBase(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

class AppConfigCreate(AppConfigBase):
    pass

class AppConfigUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None

class AppConfigOut(AppConfigBase):
    class Config:
        from_attributes = True

class TaskPage(BaseModel):
    items: List[TaskOut]
    total: int

class TaskRunOut(APIModel):
    id: uuid.UUID
    task_id: str
    run_mode: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    params_snapshot: Optional[Dict[str, Any]] = None

    class Config(APIModel.Config):
        from_attributes = True

class TaskHistoryPage(BaseModel):
    items: List[TaskRunOut]
    total: int

class UserBase(APIModel):
    username: str
    role: Optional[str] = "user"

class UserRegister(BaseModel):
    username: str
    password: str

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.match(r'^[a-zA-Z0-9]+$', v):
            raise ValueError('Password can only contain letters and numbers')
        return v

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.match(r'^[a-zA-Z0-9]+$', v):
            raise ValueError('Password can only contain letters and numbers')
        return v

class UserOut(UserBase):
    id: uuid.UUID
    created_at: datetime
    
    class Config(APIModel.Config):
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class SystemStatOut(APIModel):
    ts: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    net_sent: int
    net_recv: int

    class Config(APIModel.Config):
        from_attributes = True
