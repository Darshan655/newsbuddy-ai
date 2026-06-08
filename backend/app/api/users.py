from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import get_db, User
from app.models.schemas import UserCreate, UserUpdate, UserResponse

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (signup via WhatsApp or web)."""
    existing = db.query(User).filter(User.phone_number == user_in.phone_number).first()
    if existing:
        raise HTTPException(status_code=409, detail="Phone number already registered")

    user = User(
        phone_number=user_in.phone_number,
        whatsapp_number=user_in.whatsapp_number or user_in.phone_number,
        name=user_in.name,
        city=user_in.city,
        state=user_in.state,
        country=user_in.country,
        language=user_in.language,
        preferred_call_time=user_in.preferred_call_time,
        topics=user_in.topics,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/", response_model=List[UserResponse])
def list_users(
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List users, optionally filtered by city or status. Admin use."""
    q = db.query(User)
    if city:
        q = q.filter(User.city.ilike(f"%{city}%"))
    if status:
        q = q.filter(User.status == status)
    return q.offset(skip).limit(limit).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a single user's profile."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/by-phone/{phone_number}", response_model=UserResponse)
def get_user_by_phone(phone_number: str, db: Session = Depends(get_db)):
    """Look up a user by phone number (used by WhatsApp bot)."""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    """Update user preferences."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Delete (or deactivate) a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Soft delete
    user.status = "inactive"
    db.commit()
    return None
