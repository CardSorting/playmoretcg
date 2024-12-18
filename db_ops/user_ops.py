from typing import Optional, Dict, Any
from database import get_db
from models import User
from sqlalchemy.orm import Session
from sqlalchemy import select

def get_user(user_id, db: Session = next(get_db())) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    return user.__dict__ if user else None

def create_user(user_id, user_data: Dict[str, Any], db: Session = next(get_db())) -> Dict[str, Any]:
    """Create a new user."""
    user = User(**user_data)
    user.id = user_id
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.__dict__

def update_user(user_id, user_data: Dict[str, Any], db: Session = next(get_db())) -> Dict[str, Any]:
    """Update user data."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    if user:
        for key, value in user_data.items():
            setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return user.__dict__
    return None

def delete_user(user_id, db: Session = next(get_db())) -> bool:
    """Delete user and all their cards."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

def get_user_credits(user_id, db: Session = next(get_db())) -> int:
    """Get user's current credit balance."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    return user.credits if user else 0

def add_credits(user_id, amount: int, db: Session = next(get_db())) -> int:
    """Add credits to user's balance."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    if user:
        user.credits += amount
        db.commit()
        db.refresh(user)
        return user.credits
    return 0

def deduct_credits(user_id, amount: int, db: Session = next(get_db())) -> bool:
    """Deduct credits from user's balance if sufficient funds exist."""
    user = db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()
    if user and user.credits >= amount:
        user.credits -= amount
        db.commit()
        db.refresh(user)
        return True
    return False