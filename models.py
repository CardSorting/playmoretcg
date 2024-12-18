from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, event, Enum, Float, Boolean, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
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

class ListingStatus(enum.Enum):
    ACTIVE = "Active"
    SOLD = "Sold"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"

class ListingType(enum.Enum):
    FIXED_PRICE = "Fixed Price"
    AUCTION = "Auction"

class ListingDuration(enum.Enum):
    ONE_HOUR = "1 Hour"
    SIX_HOURS = "6 Hours"
    TWELVE_HOURS = "12 Hours"
    ONE_DAY = "24 Hours"
    THREE_DAYS = "3 Days"
    SEVEN_DAYS = "7 Days"

    @classmethod
    def get_timedelta(cls, duration):
        duration_map = {
            cls.ONE_HOUR: timedelta(hours=1),
            cls.SIX_HOURS: timedelta(hours=6),
            cls.TWELVE_HOURS: timedelta(hours=12),
            cls.ONE_DAY: timedelta(days=1),
            cls.THREE_DAYS: timedelta(days=3),
            cls.SEVEN_DAYS: timedelta(days=7)
        }
        return duration_map.get(duration)

class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey('listings.id', ondelete='CASCADE'), nullable=False)
    bidder_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    listing = relationship("Listing", back_populates="bids")
    bidder = relationship("User", back_populates="bids")

    def to_dict(self):
        """Convert bid to dictionary."""
        return {
            'id': self.id,
            'listing_id': self.listing_id,
            'bidder_id': self.bidder_id,
            'amount': self.amount,
            'created_at': self.created_at.isoformat(),
            'bidder': {
                'id': self.bidder.id,
                'display_name': self.bidder.display_name
            } if self.bidder else None
        }

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Firebase UID
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    display_name = Column(String, nullable=True)
    credits = Column(Integer, default=100, nullable=False)  # Starting credits for new users
    
    # Relationships
    cards = relationship("Card", back_populates="user", cascade="all, delete-orphan")
    listings = relationship("Listing", back_populates="seller", foreign_keys="Listing.seller_id")
    purchases = relationship("Listing", back_populates="buyer", foreign_keys="Listing.buyer_id")
    bids = relationship("Bid", back_populates="bidder")
    
    @classmethod
    def create_from_firebase(cls, firebase_user):
        """Create a User instance from Firebase user data."""
        return cls(
            id=firebase_user.uid,
            email=firebase_user.email,
            display_name=firebase_user.display_name,
            credits=100  # Give new users 100 credits
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

    def add_credits(self, db_session, amount):
        """Add credits to user's balance."""
        self.credits += amount
        db_session.commit()
        return self.credits

    def deduct_credits(self, db_session, amount):
        """Deduct credits from user's balance if sufficient funds exist."""
        if self.credits >= amount:
            self.credits -= amount
            db_session.commit()
            return True
        return False

    def get_credits(self):
        """Get user's current credit balance."""
        return self.credits

    def place_bid(self, db_session, listing, amount):
        """Place a bid on an auction listing."""
        if listing.listing_type != ListingType.AUCTION:
            raise ValueError("Listing is not an auction")
            
        if listing.status != ListingStatus.ACTIVE:
            raise ValueError("Auction is not active")
            
        if listing.is_expired:
            raise ValueError("Auction has ended")
            
        if listing.seller_id == self.id:
            raise ValueError("Cannot bid on your own auction")
            
        if amount <= listing.current_price:
            raise ValueError(f"Bid must be higher than current price: {listing.current_price}")
            
        # Check if user has enough credits
        if not self.deduct_credits(db_session, amount):
            raise ValueError("Insufficient credits")
            
        # Refund previous bidder if exists
        if listing.current_bid:
            previous_bidder = listing.current_bid.bidder
            previous_bidder.add_credits(db_session, listing.current_bid.amount)
            
        # Create new bid
        bid = Bid(
            listing_id=listing.id,
            bidder_id=self.id,
            amount=amount
        )
        db_session.add(bid)
        db_session.commit()
        return bid

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
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    # Relationships
    user = relationship("User", back_populates="cards")
    images = relationship("CardImage", back_populates="card", cascade="all, delete-orphan")
    listing = relationship("Listing", back_populates="card", uselist=False)

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
            'user_id': self.user_id,
            'is_listed': self.listing is not None and self.listing.status == ListingStatus.ACTIVE
        }

class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'), nullable=False)
    seller_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    buyer_id = Column(String, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    listing_type = Column(Enum(ListingType), nullable=False)
    price = Column(Float, nullable=False)  # Starting price for auctions, fixed price for direct sales
    status = Column(Enum(ListingStatus), default=ListingStatus.ACTIVE, nullable=False)
    duration = Column(Enum(ListingDuration), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)
    
    # Relationships
    card = relationship("Card", back_populates="listing")
    seller = relationship("User", back_populates="listings", foreign_keys=[seller_id])
    buyer = relationship("User", back_populates="purchases", foreign_keys=[buyer_id])
    bids = relationship("Bid", back_populates="listing", cascade="all, delete-orphan", order_by="desc(Bid.amount)")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.duration and not self.expires_at:
            self.expires_at = datetime.utcnow() + ListingDuration.get_timedelta(self.duration)

    @property
    def is_expired(self):
        """Check if the listing has expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def current_bid(self):
        """Get the current highest bid."""
        return self.bids[0] if self.bids else None

    @property
    def current_price(self):
        """Get the current price (highest bid for auctions, fixed price for direct sales)."""
        if self.listing_type == ListingType.AUCTION:
            return self.current_bid.amount if self.current_bid else self.price
        return self.price

    def to_dict(self):
        """Convert listing to dictionary."""
        return {
            'id': self.id,
            'card_id': self.card_id,
            'seller_id': self.seller_id,
            'buyer_id': self.buyer_id,
            'listing_type': self.listing_type.value,
            'price': self.price,
            'current_price': self.current_price,
            'status': self.status.value,
            'duration': self.duration.value,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'sold_at': self.sold_at.isoformat() if self.sold_at else None,
            'time_left': str(self.expires_at - datetime.utcnow()) if self.expires_at > datetime.utcnow() else "Expired",
            'card': self.card.to_dict() if self.card else None,
            'seller': {
                'id': self.seller.id,
                'display_name': self.seller.display_name
            } if self.seller else None,
            'buyer': {
                'id': self.buyer.id,
                'display_name': self.buyer.display_name
            } if self.buyer else None,
            'bids': [bid.to_dict() for bid in self.bids],
            'bid_count': len(self.bids)
        }

    def finalize_auction(self, db_session):
        """Finalize an auction when it expires."""
        if self.listing_type != ListingType.AUCTION:
            raise ValueError("Listing is not an auction")
            
        if not self.is_expired:
            raise ValueError("Auction has not ended yet")
            
        if self.status != ListingStatus.ACTIVE:
            raise ValueError("Auction is not active")
            
        winning_bid = self.current_bid
        if winning_bid:
            # Update listing status
            self.status = ListingStatus.SOLD
            self.buyer_id = winning_bid.bidder_id
            self.sold_at = datetime.utcnow()
            
            # Transfer card ownership
            self.card.user_id = winning_bid.bidder_id
            
            # Transfer credits to seller
            self.seller.add_credits(db_session, winning_bid.amount)
        else:
            # No bids, auction expires
            self.status = ListingStatus.EXPIRED
            
        db_session.commit()
        return self

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

def create_listing(db_session, card_id: int, seller_id: str, price: float, duration: ListingDuration, listing_type: ListingType = ListingType.FIXED_PRICE) -> Listing:
    """Create a new listing for a card."""
    try:
        # Check if card exists and belongs to seller
        card = db_session.query(Card).filter_by(id=card_id, user_id=seller_id).first()
        if not card:
            raise ValueError("Card not found or doesn't belong to seller")
            
        # Check if card is already listed
        existing_listing = db_session.query(Listing).filter_by(
            card_id=card_id,
            status=ListingStatus.ACTIVE
        ).first()
        if existing_listing:
            raise ValueError("Card is already listed")
            
        listing = Listing(
            card_id=card_id,
            seller_id=seller_id,
            price=price,
            duration=duration,
            listing_type=listing_type
        )
        db_session.add(listing)
        db_session.commit()
        return listing
    except Exception as e:
        print(f"Error creating listing: {e}")
        db_session.rollback()
        raise e

def check_expired_listings(db_session):
    """Check and update expired listings."""
    try:
        expired_listings = db_session.query(Listing).filter(
            Listing.status == ListingStatus.ACTIVE,
            Listing.expires_at <= datetime.utcnow()
        ).all()
        
        for listing in expired_listings:
            if listing.listing_type == ListingType.AUCTION:
                listing.finalize_auction(db_session)
            else:
                listing.status = ListingStatus.EXPIRED
            
        db_session.commit()
        return expired_listings
    except Exception as e:
        print(f"Error checking expired listings: {e}")
        db_session.rollback()
        raise e