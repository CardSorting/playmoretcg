from typing import Optional, Dict, Any, List
from datetime import datetime
from firestore_db_ops.firestore_init import db, listing_to_dict, logger
from models import ListingStatus, ListingType, ListingDuration
from firestore_db_ops.bid_ops import finalize_auction, get_listing_bids

def create_listing(card_id: str, seller_id: str, price: float, duration: str, listing_type: str = ListingType.FIXED_PRICE.value) -> Dict[str, Any]:
    """Create a new listing for a card."""
    try:
        # Check if card exists and belongs to seller
        from firestore_db_ops.card_ops import get_card
        card = get_card(card_id)
        if not card or card.get('user_id') != seller_id:
            raise ValueError("Card not found or doesn't belong to seller")
        
        # Check if card is already listed
        existing_listings = db.collection('listings').where(
            'card_id', '==', card_id
        ).where('status', '==', ListingStatus.ACTIVE.value).stream()
        if list(existing_listings):
            raise ValueError("Card is already listed")
        
        listing_data = {
            'card_id': card_id,
            'seller_id': seller_id,
            'price': price,
            'current_price': price,
            'duration': duration,
            'listing_type': listing_type,
            'status': ListingStatus.ACTIVE.value,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + ListingDuration.get_timedelta(ListingDuration(duration)),
            'bid_count': 0
        }
        
        listing_ref = db.collection('listings').document()
        listing_dict = listing_to_dict(listing_data)
        listing_ref.set(listing_dict)
        
        # Add ID to the returned dictionary
        listing_dict['id'] = listing_ref.id
        return listing_dict
        
    except Exception as e:
        logger.error(f"Error creating listing: {e}")
        raise

def get_listing(listing_id: str) -> Optional[Dict[str, Any]]:
    """Get listing by ID."""
    doc = db.collection('listings').document(listing_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Check if listing has expired
        if data['status'] == ListingStatus.ACTIVE.value:
            expires_at = data['expires_at'].replace(tzinfo=None)
            if datetime.utcnow() > expires_at:
                if data['listing_type'] == ListingType.AUCTION.value:
                    finalize_auction(listing_id)
                else:
                    update_listing_status(listing_id, ListingStatus.EXPIRED.value)
                data = get_listing(listing_id)
                
        # Get bids for auctions
        if data['listing_type'] == ListingType.AUCTION.value:
            data['bids'] = get_listing_bids(listing_id)
                
        return data
    return None

def get_active_listings(limit: int = 20, listing_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get active listings."""
    listings = []
    now = datetime.utcnow()
    
    # Build query
    query = db.collection('listings').where('status', '==', ListingStatus.ACTIVE.value)
    if listing_type:
        query = query.where('listing_type', '==', listing_type)
    query = query.where('expires_at', '>', now).limit(limit)
    
    for doc in query.stream():
        listing_data = doc.to_dict()
        listing_data['id'] = doc.id
        
        # Calculate time left
        expires_at = listing_data['expires_at'].replace(tzinfo=None)
        listing_data['time_left'] = str(expires_at - now)
        
        # Get card details
        from firestore_db_ops.card_ops import get_card
        card = get_card(listing_data['card_id'])
        if card:
            listing_data['card'] = card
            
        # Get seller details
        from firestore_db_ops.user_ops import get_user
        seller = get_user(listing_data['seller_id'])
        if seller:
            listing_data['seller'] = {
                'id': listing_data['seller_id'],
                'display_name': seller.get('display_name')
            }
            
        # Get bids for auctions
        if listing_data['listing_type'] == ListingType.AUCTION.value:
            listing_data['bids'] = get_listing_bids(doc.id)
            
        listings.append(listing_data)
    
    return listings

def check_expired_listings() -> List[Dict[str, Any]]:
    """Check and update expired listings."""
    try:
        now = datetime.utcnow()
        expired_query = db.collection('listings').where(
            'status', '==', ListingStatus.ACTIVE.value
        ).where('expires_at', '<=', now)
        
        expired_listings = []
        
        for doc in expired_query.stream():
            listing_data = doc.to_dict()
            listing_data['id'] = doc.id
            
            if listing_data['listing_type'] == ListingType.AUCTION.value:
                finalize_auction(doc.id)
            else:
                update_listing_status(doc.id, ListingStatus.EXPIRED.value)
                
            expired_listings.append(listing_data)
            
        return expired_listings
        
    except Exception as e:
        logger.error(f"Error checking expired listings: {e}")
        raise

def update_listing_status(listing_id: str, new_status: str) -> Dict[str, Any]:
    """Update listing status."""
    listing_ref = db.collection('listings').document(listing_id)
    listing_ref.update({
        'status': new_status,
        'updated_at': datetime.utcnow()
    })
    return get_listing(listing_id)