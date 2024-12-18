from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, ForeignKey, Enum
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
from typing import Dict, Any
import logging
import enum

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define the database URL
DATABASE_URL = "sqlite:///playmoretcg.db"

# Create a SQLAlchemy engine
engine = create_engine(DATABASE_URL)

# Create a base for declarative models
Base = declarative_base()

# Define enums
class ListingType(enum.Enum):
    SALE = "sale"
    AUCTION = "auction"

class ListingStatus(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    SOLD = "sold"

# Define the User model
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    display_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    credits = Column(Integer, default=100)
    cards = relationship("Card", back_populates="user")

# Define the Card model
class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    manaCost = Column(String)
    type = Column(String)
    color = Column(String)
    abilities = Column(String)
    flavorText = Column(String)
    rarity = Column(String)
    set_name = Column(String)
    card_number = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    images = Column(String) # Store image URLs as a string, comma separated
    user = relationship("User", back_populates="cards")
    listings = relationship("Listing", back_populates="card")

# Define the Bid model
class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"))
    bidder_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    listing = relationship("Listing", back_populates="bids")
    bidder = relationship("User")

# Define the Listing model
class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"))
    seller_id = Column(Integer, ForeignKey("users.id"))
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    listing_type = Column(Enum(ListingType))
    price = Column(Float)
    current_price = Column(Float)
    status = Column(Enum(ListingStatus), default=ListingStatus.OPEN)
    duration = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)
    bid_count = Column(Integer, default=0)
    card = relationship("Card", back_populates="listings")
    seller = relationship("User", foreign_keys=[seller_id])
    buyer = relationship("User", foreign_keys=[buyer_id])
    bids = relationship("Bid", back_populates="listing")

# Create the database tables
Base.metadata.create_all(engine)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def user_to_dict(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert user data to a dictionary."""
    return {
        'email': user_data.get('email'),
        'display_name': user_data.get('display_name'),
        'created_at': user_data.get('created_at', datetime.utcnow()),
        'last_login': datetime.utcnow(),
        'credits': user_data.get('credits', 100)
    }

def card_to_dict(card_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert card data to a dictionary."""
    return {
        'name': card_data.get('name'),
        'manaCost': card_data.get('manaCost'),
        'type': card_data.get('type'),
        'color': card_data.get('color'),
        'abilities': card_data.get('abilities'),
        'flavorText': card_data.get('flavorText'),
        'rarity': card_data.get('rarity'),
        'set_name': card_data.get('set_name'),
        'card_number': card_data.get('card_number'),
        'created_at': card_data.get('created_at', datetime.utcnow()),
        'user_id': card_data.get('user_id'),
        'images': card_data.get('images', [])
    }

def bid_to_dict(bid_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert bid data to a dictionary."""
    return {
        'listing_id': bid_data.get('listing_id'),
        'bidder_id': bid_data.get('bidder_id'),
        'amount': bid_data.get('amount'),
        'created_at': bid_data.get('created_at', datetime.utcnow())
    }

def listing_to_dict(listing_data: Dict[str, Any], include_bids: bool = False) -> Dict[str, Any]:
    """Convert listing data to a dictionary."""
    now = datetime.utcnow()
    duration = listing_data.get('duration')
    expires_at = listing_data.get('expires_at', now)
    
    listing_dict = {
        'card_id': listing_data.get('card_id'),
        'seller_id': listing_data.get('seller_id'),
        'buyer_id': listing_data.get('buyer_id'),
        'listing_type': listing_data.get('listing_type'),
        'price': listing_data.get('price'),
        'current_price': listing_data.get('current_price', listing_data.get('price')),
        'status': listing_data.get('status'),
        'duration': duration,
        'created_at': listing_data.get('created_at', now),
        'expires_at': expires_at,
        'updated_at': now,
        'sold_at': listing_data.get('sold_at'),
        'time_left': str(expires_at - now) if expires_at > now else "Expired",
        'bid_count': listing_data.get('bid_count', 0)
    }
    
    if include_bids:
        listing_dict['bids'] = listing_data.get('bids', [])
        
    return listing_dict