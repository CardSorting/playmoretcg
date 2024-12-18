from typing import Optional, Dict, Any, List
from datetime import datetime
from firestore_db_ops.firestore_init import get_db, listing_to_dict, logger, Listing, ListingType, ListingStatus, Card, User
from models import ListingDuration
from firestore_db_ops.bid_ops import finalize_auction, get_listing_bids
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import NoResultFound

def create_listing(card_id: int, seller_id: int, price: float, duration: str, listing_type: str = ListingType.SALE.value, db: Session = next(get_db())) -> Dict[str, Any]:
    """Create a new listing for a card."""
    try:
        # Check if card exists and belongs to seller
        from firestore_db_ops.card_ops import get_card
        card = get_card(card_id, db=db)
        if not card or card.get('user_id') != seller_id:
            raise ValueError("Card not found or doesn't belong to seller")

        # Check if card is already listed
        existing_listings = db.execute(select(Listing).filter(Listing.card_id == card_id, Listing.status == ListingStatus.OPEN)).scalars().all()
        if existing_listings:
            raise ValueError("Card is already listed")

        listing_data = {
            'card_id': card_id,
            'seller_id': seller_id,
            'price': price,
            'current_price': price,
            'duration': duration,
            'listing_type': ListingType(listing_type),
            'status': ListingStatus.OPEN,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + ListingDuration.get_timedelta(ListingDuration(duration)),
            'bid_count': 0
        }

        listing_dict = listing_to_dict(listing_data)
        listing = Listing(**listing_dict)
        db.add(listing)
        db.commit()
        db.refresh(listing)
        listing_dict['id'] = listing.id
        return listing_dict

    except Exception as e:
        logger.error(f"Error creating listing: {e}")
        raise

def get_listing(listing_id: int, db: Session = next(get_db())) -> Optional[Dict[str, Any]]:
    """Get listing by ID."""
    listing = db.execute(select(Listing).filter(Listing.id == listing_id)).scalar_one_or_none()
    if listing:
        listing_data = listing.__dict__
        # Check if listing has expired
        if listing_data['status'] == ListingStatus.OPEN:
            if datetime.utcnow() > listing_data['expires_at']:
                if listing_data['listing_type'] == ListingType.AUCTION:
                    finalize_auction(listing_id, db=db)
                else:
                    update_listing_status(listing_id, ListingStatus.EXPIRED.value, db=db)
                listing = db.execute(select(Listing).filter(Listing.id == listing_id)).scalar_one_or_none()
                if listing:
                    listing_data = listing.__dict__
        # Get bids for auctions
        if listing_data['listing_type'] == ListingType.AUCTION:
            listing_data['bids'] = get_listing_bids(listing_id, db=db)
        return listing_data
    return None

def get_active_listings(limit: int = 20, listing_type: Optional[str] = None, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Get active listings."""
    now = datetime.utcnow()
    query = select(Listing).filter(Listing.status == ListingStatus.OPEN, Listing.expires_at > now)
    if listing_type:
        query = query.filter(Listing.listing_type == ListingType(listing_type))
    listings = db.execute(query.order_by(Listing.created_at.desc()).limit(limit)).scalars().all()
    
    result = []
    for listing in listings:
        listing_data = listing.__dict__
        listing_data['time_left'] = str(listing_data['expires_at'] - now)
        
        # Get card details
        from firestore_db_ops.card_ops import get_card
        card = get_card(listing_data['card_id'], db=db)
        if card:
            listing_data['card'] = card
            
        # Get seller details
        from firestore_db_ops.user_ops import get_user
        seller = get_user(listing_data['seller_id'], db=db)
        if seller:
            listing_data['seller'] = {
                'id': listing_data['seller_id'],
                'display_name': seller.get('display_name')
            }
        
        # Get bids for auctions
        if listing_data['listing_type'] == ListingType.AUCTION:
            listing_data['bids'] = get_listing_bids(listing.id, db=db)
        
        result.append(listing_data)
    
    return result

def check_expired_listings(db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Check and update expired listings."""
    try:
        now = datetime.utcnow()
        expired_listings = db.execute(select(Listing).filter(Listing.status == ListingStatus.OPEN, Listing.expires_at <= now)).scalars().all()
        
        result = []
        for listing in expired_listings:
            listing_data = listing.__dict__
            if listing_data['listing_type'] == ListingType.AUCTION:
                finalize_auction(listing.id, db=db)
            else:
                update_listing_status(listing.id, ListingStatus.EXPIRED.value, db=db)
            result.append(listing_data)
        return result
    except Exception as e:
        logger.error(f"Error checking expired listings: {e}")
        raise

def update_listing_status(listing_id: int, new_status: str, db: Session = next(get_db())) -> Dict[str, Any]:
    """Update listing status."""
    listing = db.execute(select(Listing).filter(Listing.id == listing_id)).scalar_one_or_none()
    if listing:
        listing.status = ListingStatus(new_status)
        listing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(listing)
        return listing.__dict__
    return None