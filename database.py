from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any

# Load environment variables first
load_dotenv()

SQLALCHEMY_DATABASE_URL = "sqlite:///./cards.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@contextmanager
def get_db():
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database."""
    from models import Base
    Base.metadata.create_all(bind=engine)

def get_user_by_firebase_id(db, firebase_uid):
    """Get user by Firebase UID."""
    from models import User
    return db.query(User).filter(User.id == firebase_uid).first()

def create_user(db, firebase_user):
    """Create a new user from Firebase user data."""
    from models import User
    user = User.create_from_firebase(firebase_user)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_or_create_user(db, firebase_user):
    """Get existing user or create new one."""
    from models import User
    user = get_user_by_firebase_id(db, firebase_user.uid)
    if not user:
        user = create_user(db, firebase_user)
    return user

def sync_user(db, firebase_user):
    """Sync user data from Firebase."""
    from models import User
    user = get_user_by_firebase_id(db, firebase_user.uid)
    if user:
        user.email = firebase_user.email
        user.display_name = firebase_user.display_name
        user.last_login = datetime.utcnow()
        db.commit()
    else:
        user = create_user(db, firebase_user)
    return user

def get_user_cards(db, user_id):
    """Get all cards for a user."""
    from models import Card
    return db.query(Card).filter(Card.user_id == user_id).all()

def create_card_for_user(db, user_id: str, card_data: Dict[str, Any], image_url: Optional[str] = None, filename: Optional[str] = None) -> Any:
    """
    Create a new card with optional image for a user.
    
    Args:
        db: Database session
        user_id: User ID (Firebase UID)
        card_data: Dictionary containing card data
        image_url: Optional Backblaze URL for card image
        filename: Optional filename for card image
        
    Returns:
        Card: Created card object
    """
    from models import Card, CardImage
    try:
        # Create card
        card = Card(user_id=user_id, **card_data)
        db.add(card)
        db.flush()  # Get card ID without committing
        
        # Add image if provided
        if image_url and filename:
            image = CardImage(
                card_id=card.id,
                backblaze_url=image_url,
                filename=filename
            )
            db.add(image)
        
        db.commit()
        db.refresh(card)
        return card
    except Exception as e:
        print(f"Error creating card: {e}")
        db.rollback()
        raise e

def get_card(db, card_id: int, user_id: Optional[str] = None) -> Any:
    """
    Get a card by ID, optionally filtering by user.
    
    Args:
        db: Database session
        card_id: Card ID
        user_id: Optional user ID to filter by
        
    Returns:
        Card: Card object if found, None otherwise
    """
    from models import Card
    query = db.query(Card).filter(Card.id == card_id)
    if user_id:
        query = query.filter(Card.user_id == user_id)
    return query.first()

def delete_card(db, card_id: int, user_id: str) -> bool:
    """
    Delete a card.
    
    Args:
        db: Database session
        card_id: Card ID
        user_id: User ID
        
    Returns:
        bool: True if card was deleted, False otherwise
    """
    from models import Card
    card = get_card(db, card_id, user_id)
    if card:
        db.delete(card)
        db.commit()
        return True
    return False

def get_random_cards(db, limit: int = 6) -> list:
    """
    Get random cards from the database.
    
    Args:
        db: Database session
        limit: Maximum number of cards to return
        
    Returns:
        list: List of random Card objects
    """
    from models import Card
    return db.query(Card).order_by(func.random()).limit(limit).all()

# Initialize database on import
init_db()