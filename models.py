from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, event, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import firebase_admin
from firebase_admin import auth
from backblaze_config import delete_image
import os

Base = declarative_base()

class Rarity(enum.Enum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    MYTHIC_RARE = "Mythic Rare"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Firebase UID
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    display_name = Column(String, nullable=True)
    
    # Relationships
    cards = relationship("Card", back_populates="user", cascade="all, delete-orphan")
    
    @classmethod
    def create_from_firebase(cls, firebase_user):
        """Create a User instance from Firebase user data."""
        return cls(
            id=firebase_user.uid,
            email=firebase_user.email,
            display_name=firebase_user.display_name
        )
    
    @classmethod
    def get_or_create(cls, db_session, firebase_user):
        """Get existing user or create new one from Firebase user data."""
        user = db_session.query(cls).filter_by(id=firebase_user.uid).first()
        if not user:
            user = cls.create_from_firebase(firebase_user)
            db_session.add(user)
            db_session.commit()
        return user
    
    def update_last_login(self, db_session):
        """Update user's last login time."""
        self.last_login = datetime.utcnow()
        db_session.commit()

class CardImage(Base):
    __tablename__ = "card_images"

    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'), nullable=False)
    backblaze_url = Column(String(500), nullable=False)  # Backblaze B2 URL
    filename = Column(String(255), nullable=False)  # Original filename in Backblaze
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    card = relationship("Card", back_populates="images")

    def get_url(self):
        """Get the image URL, falling back to local path if Backblaze URL is not available."""
        if self.backblaze_url:
            return self.backblaze_url
        return f"/static/card_images/{self.filename}"

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    manaCost = Column(String(50))
    type = Column(String(100))
    color = Column(String(50))
    abilities = Column(Text)
    flavorText = Column(Text)
    rarity = Column(Enum(Rarity), nullable=False)
    set_name = Column(String(10))
    card_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign key to user
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="cards")
    images = relationship("CardImage", back_populates="card", cascade="all, delete-orphan")

    @property
    def primary_image_url(self):
        """Get the URL of the primary (first) image."""
        if self.images:
            return self.images[0].get_url()
        return "/static/default-card.png"

    def add_image(self, db_session, backblaze_url, filename):
        """Add a new image to the card."""
        image = CardImage(
            card_id=self.id,
            backblaze_url=backblaze_url,
            filename=filename
        )
        db_session.add(image)
        db_session.commit()
        return image

    def to_dict(self):
        """Convert card to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'manaCost': self.manaCost,
            'type': self.type,
            'color': self.color,
            'abilities': self.abilities,
            'flavorText': self.flavorText,
            'rarity': self.rarity.value,
            'set_name': self.set_name,
            'card_number': self.card_number,
            'image_url': self.primary_image_url,
            'created_at': self.created_at.isoformat(),
            'user_id': self.user_id
        }

# Event listeners
@event.listens_for(CardImage, 'after_delete')
def delete_card_image(mapper, connection, target):
    """Delete image from Backblaze when CardImage record is deleted."""
    if target.filename:
        delete_image(target.filename)

@event.listens_for(User, 'after_delete')
def user_after_delete(mapper, connection, target):
    """Clean up user data when user is deleted."""
    try:
        # Delete user from Firebase if they exist
        auth.delete_user(target.id)
    except Exception as e:
        print(f"Error deleting Firebase user: {e}")

def sync_user_from_firebase(db_session, firebase_uid):
    """Sync user data from Firebase to local database."""
    try:
        firebase_user = auth.get_user(firebase_uid)
        user = db_session.query(User).filter_by(id=firebase_uid).first()
        
        if user:
            user.email = firebase_user.email
            user.display_name = firebase_user.display_name
            user.last_login = datetime.utcnow()
        else:
            user = User.create_from_firebase(firebase_user)
            db_session.add(user)
        
        db_session.commit()
        return user
        
    except Exception as e:
        print(f"Error syncing user from Firebase: {e}")
        db_session.rollback()
        raise e

def create_card_for_user(db_session, user_id, card_data, image_url=None, filename=None):
    """Create a new card with optional image for a user."""
    try:
        # Convert string rarity to enum
        if isinstance(card_data.get('rarity'), str):
            card_data['rarity'] = Rarity[card_data['rarity'].upper().replace(' ', '_')]
        
        # Create card
        card = Card(user_id=user_id, **card_data)
        db_session.add(card)
        db_session.flush()  # Get card ID without committing
        
        # Add image if provided
        if image_url and filename:
            card.add_image(db_session, image_url, filename)
        
        db_session.commit()
        return card
    except Exception as e:
        print(f"Error creating card: {e}")
        db_session.rollback()
        raise e

def get_user_cards(db_session, user_id):
    """Get all cards for a user."""
    return db_session.query(Card).filter_by(user_id=user_id).all()