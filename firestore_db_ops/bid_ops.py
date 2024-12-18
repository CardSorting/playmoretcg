from typing import Optional, Dict, Any, List
from datetime import datetime
from firestore_db_ops.firestore_init import db, bid_to_dict, logger
from models import ListingType, ListingStatus
from firestore_db_ops.user_ops import deduct_credits, add_credits, get_user
from firebase_admin import firestore

def create_bid(listing_id: str, bidder_id: str, amount: float) -> Dict[str, Any]:
    """Create a new bid for an auction listing."""
    try:
        # Get listing
        from firestore_db_ops.listing_ops import get_listing
        listing = get_listing(listing_id)
        if not listing:
            raise ValueError("Listing not found")
            
        if listing['listing_type'] != ListingType.AUCTION.value:
            raise ValueError("Listing is not an auction")
            
        if listing['status'] != ListingStatus.ACTIVE.value:
            raise ValueError("Auction is not active")
            
        expires_at = listing['expires_at'].replace(tzinfo=None)
        if datetime.utcnow() > expires_at:
            raise ValueError("Auction has ended")
            
        if listing['seller_id'] == bidder_id:
            raise ValueError("Cannot bid on your own auction")
            
        if amount <= listing['current_price']:
            raise ValueError(f"Bid must be higher than current price: {listing['current_price']}")
            
        # Check if bidder has enough credits
        if not deduct_credits(bidder_id, amount):
            raise ValueError("Insufficient credits")
            
        # Refund previous high bidder if exists
        previous_bids = db.collection('bids').where(
            'listing_id', '==', listing_id
        ).order_by('amount', direction=firestore.Query.DESCENDING).limit(1).stream()
        
        previous_bid = next(previous_bids, None)
        if previous_bid:
            previous_bid_data = previous_bid.to_dict()
            add_credits(previous_bid_data['bidder_id'], previous_bid_data['amount'])
            
        # Create new bid
        bid_data = {
            'listing_id': listing_id,
            'bidder_id': bidder_id,
            'amount': amount,
            'created_at': datetime.utcnow()
        }
        
        bid_ref = db.collection('bids').document()
        bid_dict = bid_to_dict(bid_data)
        bid_ref.set(bid_dict)
        
        # Update listing current price and bid count
        listing_ref = db.collection('listings').document(listing_id)
        listing_ref.update({
            'current_price': amount,
            'bid_count': firestore.Increment(1),
            'updated_at': datetime.utcnow()
        })
        
        # Add ID to the returned dictionary
        bid_dict['id'] = bid_ref.id
        return bid_dict
        
    except Exception as e:
        logger.error(f"Error creating bid: {e}")
        raise

def get_listing_bids(listing_id: str) -> List[Dict[str, Any]]:
    """Get all bids for a listing."""
    bids = []
    query = db.collection('bids').where(
        'listing_id', '==', listing_id
    ).order_by('amount', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        bid_data = doc.to_dict()
        bid_data['id'] = doc.id
        
        # Get bidder details
        bidder = get_user(bid_data['bidder_id'])
        if bidder:
            bid_data['bidder'] = {
                'id': bid_data['bidder_id'],
                'display_name': bidder.get('display_name')
            }
            
        bids.append(bid_data)
        
    return bids

def finalize_auction(listing_id: str) -> Dict[str, Any]:
    """Finalize an auction when it expires."""
    try:
        from firestore_db_ops.listing_ops import get_listing
        listing = get_listing(listing_id)
        if not listing:
            raise ValueError("Listing not found")
            
        if listing['listing_type'] != ListingType.AUCTION.value:
            raise ValueError("Listing is not an auction")
            
        if listing['status'] != ListingStatus.ACTIVE.value:
            raise ValueError("Auction is not active")
            
        expires_at = listing['expires_at'].replace(tzinfo=None)
        if datetime.utcnow() <= expires_at:
            raise ValueError("Auction has not ended yet")
            
        # Get winning bid
        winning_bids = db.collection('bids').where(
            'listing_id', '==', listing_id
        ).order_by('amount', direction=firestore.Query.DESCENDING).limit(1).stream()
        
        winning_bid = next(winning_bids, None)
        if winning_bid:
            winning_bid_data = winning_bid.to_dict()
            
            # Update listing
            listing_ref = db.collection('listings').document(listing_id)
            listing_ref.update({
                'status': ListingStatus.SOLD.value,
                'buyer_id': winning_bid_data['bidder_id'],
                'sold_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })
            
            # Transfer card ownership
            from firestore_db_ops.card_ops import get_card
            card_ref = db.collection('cards').document(listing['card_id'])
            card_ref.update({
                'user_id': winning_bid_data['bidder_id']
            })
            
            # Transfer credits to seller
            add_credits(listing['seller_id'], winning_bid_data['amount'])
        else:
            # No bids, auction expires
            listing_ref = db.collection('listings').document(listing_id)
            listing_ref.update({
                'status': ListingStatus.EXPIRED.value,
                'updated_at': datetime.utcnow()
            })
            
        return get_listing(listing_id)
        
    except Exception as e:
        logger.error(f"Error finalizing auction: {e}")
        raise