from typing import Generator, Optional
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jose import jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.config import settings
from app.services.minio_service import MinioService
from app.db.models import User
from app.schemas import TokenData
from app.core import security

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)
optional_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)
external_token_header = APIKeyHeader(name="X-External-Token", auto_error=False)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_minio() -> MinioService:
    return MinioService(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        bucket=settings.MINIO_BUCKET
    )

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(reusable_oauth2)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenData(username=str(payload.get("sub")))
    except (jwt.JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    # Sub is actually user ID
    user = db.query(User).filter(User.id == token_data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

def get_current_user_for_auto_run(
    db: Session = Depends(get_db),
    external_token: Optional[str] = Depends(external_token_header),
    token: Optional[str] = Depends(optional_oauth2),
) -> User:
    if (
        external_token
        and settings.EXTERNAL_AUTORUN_TOKEN
        and secrets.compare_digest(external_token, settings.EXTERNAL_AUTORUN_TOKEN)
    ):
        user = (
            db.query(User)
            .filter(User.username == settings.EXTERNAL_AUTORUN_USERNAME)
            .first()
        )
        if not user:
            user = User(
                username=settings.EXTERNAL_AUTORUN_USERNAME,
                password_hash=security.get_password_hash(secrets.token_urlsafe(32)),
                role="external",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenData(username=str(payload.get("sub")))
    except (jwt.JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    user = db.query(User).filter(User.id == token_data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

def get_current_user_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
        )
    return current_user
