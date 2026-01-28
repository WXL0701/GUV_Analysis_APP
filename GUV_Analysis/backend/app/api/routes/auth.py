from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.core.config import settings
from app.db.models import User
from app.schemas import Token, UserOut, UserRegister

router = APIRouter()

@router.post("/register", response_model=Token)
def register(
    *,
    db: Session = Depends(deps.get_db),
    user_in: UserRegister,
) -> Any:
    """
    Register new user.
    """
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists.",
        )
    
    user = User(
        username=user_in.username,
        password_hash=security.get_password_hash(user_in.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Auto login
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/test-token", response_model=UserOut)
def test_token(current_user: User = Depends(deps.get_current_user)) -> Any:
    """
    Test access token
    """
    return current_user
