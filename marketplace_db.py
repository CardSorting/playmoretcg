from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
from models import ListingStatus
from firestore_db_ops.listing_ops import get_listing, update_listing_status
from firestore_db_ops.card_ops import get_card
from firestore_db_ops.user_ops import get_user
from firestore_db_ops.firestore_init import get_db
from sqlalchemy.orm import Session
from fastapi import Depends
from sqlalchemy import select

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_user_listings(user_id: int, status: Optional[str] = None, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get user's listings with optional status filter."""
    try:
        # Build query
        from firestore_db_ops.listing_ops import Listing
        query = select(Listing).filter(Listing.seller_id == user_id)
        if status:
            query = query.filter(Listing.status == ListingStatus(status))
        
        listings = []
        listings_data = db.execute(query).scalars().all()
        for listing in listings_data:
            listing_data = listing.__dict__
            
            # Get card details
            card = get_card(listing_data['card_id'], db=db)
            if card:
                listing_data['card'] = card
                
            # Get buyer details if sold
            if listing_data.get('buyer_id'):
                buyer = get_user(listing_data['buyer_id'], db=db)
                if buyer:
                    listing_data['buyer'] = {
                        'id': listing_data['buyer_id'],
                        'display_name': buyer.get('display_name')
                    }
            
            # Get seller details
            seller = get_user(listing_data['seller_id'], db=db)
            if seller:
                listing_data['seller'] = {
                    'id': listing_data['seller_id'],
                    'display_name': seller.get('display_name')
                }
            
            # Calculate time left for active listings
            if listing_data['status'] == ListingStatus.OPEN:
                now = datetime.utcnow()
                if now > listing_data['expires_at']:
                    update_listing_status(listing.id, ListingStatus.EXPIRED.value, db=db)
                    listing_data['status'] = ListingStatus.EXPIRED.value
                    listing_data['time_left'] = "Expired"
                else:
                    listing_data['time_left'] = str(listing_data['expires_at'] - now)
            
            listings.append(listing_data)
        
        return listings
        
    except Exception as e:
        logger.error(f"Error getting user listings: {e}")
        raise

def get_user_purchases(user_id: int, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get listings purchased by the user."""
    try:
        listings = []
        from firestore_db_ops.listing_ops import Listing
        query = select(Listing).filter(Listing.buyer_id == user_id, Listing.status == ListingStatus.SOLD)
        listings_data = db.execute(query).scalars().all()
        
        for listing in listings_data:
            listing_data = listing.__dict__
            
            # Get card details
            card = get_card(listing_data['card_id'], db=db)
            if card:
                listing_data['card'] = card
                
            # Get seller details
            seller = get_user(listing_data['seller_id'], db=db)
            if seller:
                listing_data['seller'] = {
                    'id': listing_data['seller_id'],
                    'display_name': seller.get('display_name')
                }
            
            listings.append(listing_data)
        
        return listings
        
    except Exception as e:
        logger.error(f"Error getting user purchases: {e}")
        raise

def get_user_active_bids(user_id: int, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get user's active bids on auction listings."""
    try:
        active_bids = []
        
        # Get all bids by the user
        from firestore_db_ops.bid_ops import Bid
        bids_query = select(Bid).filter(Bid.bidder_id == user_id)
        bids_data = db.execute(bids_query).scalars().all()
        
        for bid in bids_data:
            bid_data = bid.__dict__
            
            # Get listing details
            listing = get_listing(bid_data['listing_id'], db=db)
            if listing and listing['status'] == ListingStatus.OPEN.value:
                # Check if listing hasn't expired
                if datetime.utcnow() <= listing['expires_at']:
                    bid_data['listing'] = listing
                    
                    # Get bidder details
                    bidder = get_user(bid_data['bidder_id'], db=db)
                    if bidder:
                        bid_data['bidder'] = {
                            'id': bid_data['bidder_id'],
                            'display_name': bidder.get('display_name')
                        }
                    
                    active_bids.append(bid_data)
        
        return active_bids
        
    except Exception as e:
        logger.error(f"Error getting user active bids: {e}")
        raise

def get_user_bid_history(user_id: int, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get user's complete bid history."""
    try:
        bid_history = []
        from firestore_db_ops.bid_ops import Bid
        query = select(Bid).filter(Bid.bidder_id == user_id)
        bids_data = db.execute(query).scalars().all()
        
        for bid in bids_data:
            bid_data = bid.__dict__
            
            # Get listing details
            listing = get_listing(bid_data['listing_id'], db=db)
            if listing:
                bid_data['listing'] = listing
                
                # Get bidder details
                bidder = get_user(bid_data['bidder_id'], db=db)
                if bidder:
                    bid_data['bidder'] = {
                        'id': bid_data['bidder_id'],
                        'display_name': bidder.get('display_name')
                    }
                
                bid_history.append(bid_data)
        
        return sorted(
            bid_history,
            key=lambda x: x['listing']['expires_at'],
            reverse=True
        )
        
    except Exception as e:
        logger.error(f"Error getting user bid history: {e}")
        raise