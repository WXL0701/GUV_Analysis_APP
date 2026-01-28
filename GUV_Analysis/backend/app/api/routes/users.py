from typing import Any, List
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.db.models import User
from app.schemas import UserCreate, UserUpdate, UserOut

router = APIRouter()

@router.get("/", response_model=List[UserOut])
def read_users(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve users. Only admin can view all users.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.post("/", response_model=UserOut)
def create_user(
    *,
    db: Session = Depends(deps.get_db),
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new user. Only admin can create users.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    user = User(
        username=user_in.username,
        password_hash=security.get_password_hash(user_in.password),
        role=user_in.role or "user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.put("/me", response_model=UserOut)
def update_user_me(
    *,
    db: Session = Depends(deps.get_db),
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update own user (password).
    """
    if user_in.password:
        current_user.password_hash = security.get_password_hash(user_in.password)
    
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.get("/me", response_model=UserOut)
def read_user_me(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.get("/{user_id}", response_model=UserOut)
def read_user_by_id(
    user_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Get a specific user by id.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user == current_user:
        return user
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return user
