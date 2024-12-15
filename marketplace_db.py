from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
from models import ListingStatus
from firestore_db import (
    db, 
    get_card, 
    get_user, 
    update_listing_status,
    get_listing  # Import get_listing from firestore_db
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_user_listings(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get user's listings with optional status filter."""
    try:
        # Build query
        query = db.collection('listings').where('seller_id', '==', user_id)
        if status:
            query = query.where('status', '==', status)
        
        listings = []
        for doc in query.stream():
            listing_data = doc.to_dict()
            listing_data['id'] = doc.id
            
            # Get card details
            card = get_card(listing_data['card_id'])
            if card:
                listing_data['card'] = card
                
            # Get buyer details if sold
            if listing_data.get('buyer_id'):
                buyer = get_user(listing_data['buyer_id'])
                if buyer:
                    listing_data['buyer'] = {
                        'id': listing_data['buyer_id'],
                        'display_name': buyer.get('display_name')
                    }
            
            # Get seller details
            seller = get_user(listing_data['seller_id'])
            if seller:
                listing_data['seller'] = {
                    'id': listing_data['seller_id'],
                    'display_name': seller.get('display_name')
                }
            
            # Calculate time left for active listings
            if listing_data['status'] == ListingStatus.ACTIVE.value:
                expires_at = listing_data['expires_at'].replace(tzinfo=None)
                now = datetime.utcnow()
                if now > expires_at:
                    update_listing_status(doc.id, ListingStatus.EXPIRED.value)
                    listing_data['status'] = ListingStatus.EXPIRED.value
                    listing_data['time_left'] = "Expired"
                else:
                    listing_data['time_left'] = str(expires_at - now)
            
            listings.append(listing_data)
        
        return listings
        
    except Exception as e:
        logger.error(f"Error getting user listings: {e}")
        raise

def get_user_purchases(user_id: str) -> List[Dict[str, Any]]:
    """Get listings purchased by the user."""
    try:
        listings = []
        query = db.collection('listings').where(
            'buyer_id', '==', user_id
        ).where('status', '==', ListingStatus.SOLD.value)
        
        for doc in query.stream():
            listing_data = doc.to_dict()
            listing_data['id'] = doc.id
            
            # Get card details
            card = get_card(listing_data['card_id'])
            if card:
                listing_data['card'] = card
                
            # Get seller details
            seller = get_user(listing_data['seller_id'])
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

def get_user_active_bids(user_id: str) -> List[Dict[str, Any]]:
    """Get user's active bids on auction listings."""
    try:
        active_bids = []
        
        # Get all bids by the user
        bids_query = db.collection('bids').where('bidder_id', '==', user_id)
        
        for bid_doc in bids_query.stream():
            bid_data = bid_doc.to_dict()
            bid_data['id'] = bid_doc.id
            
            # Get listing details
            listing = get_listing(bid_data['listing_id'])
            if listing and listing['status'] == ListingStatus.ACTIVE.value:
                # Check if listing hasn't expired
                expires_at = listing['expires_at'].replace(tzinfo=None)
                if datetime.utcnow() <= expires_at:
                    bid_data['listing'] = listing
                    
                    # Get bidder details
                    bidder = get_user(bid_data['bidder_id'])
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

def get_user_bid_history(user_id: str) -> List[Dict[str, Any]]:
    """Get user's complete bid history."""
    try:
        bid_history = []
        query = db.collection('bids').where('bidder_id', '==', user_id)
        
        for doc in query.stream():
            bid_data = doc.to_dict()
            bid_data['id'] = doc.id
            
            # Get listing details
            listing = get_listing(bid_data['listing_id'])
            if listing:
                bid_data['listing'] = listing
                
                # Get bidder details
                bidder = get_user(bid_data['bidder_id'])
                if bidder:
                    bid_data['bidder'] = {
                        'id': bid_data['bidder_id'],
                        'display_name': bidder.get('display_name')
                    }
                
                bid_history.append(bid_data)
        
        return sorted(
            bid_history,
            key=lambda x: x['listing']['expires_at'].replace(tzinfo=None),
            reverse=True
        )
        
    except Exception as e:
        logger.error(f"Error getting user bid history: {e}")
        raise