from typing import Optional, Dict, Any, List
from datetime import datetime
from firestore_db_ops.firestore_init import get_db, bid_to_dict, logger, Bid, Listing, ListingType, ListingStatus, Card, User
from models import ListingDuration
from firestore_db_ops.user_ops import deduct_credits, add_credits, get_user
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from sqlalchemy.exc import NoResultFound

def create_bid(listing_id: int, bidder_id: int, amount: float, db: Session = next(get_db())) -> Dict[str, Any]:
    """Create a new bid for an auction listing."""
    try:
        # Get listing
        from firestore_db_ops.listing_ops import get_listing
        listing = get_listing(listing_id, db=db)
        if not listing:
            raise ValueError("Listing not found")

        if listing['listing_type'] != ListingType.AUCTION.value:
            raise ValueError("Listing is not an auction")

        if listing['status'] != ListingStatus.OPEN.value:
            raise ValueError("Auction is not active")

        if datetime.utcnow() > listing['expires_at']:
            raise ValueError("Auction has ended")

        if listing['seller_id'] == bidder_id:
            raise ValueError("Cannot bid on your own auction")

        if amount <= listing['current_price']:
            raise ValueError(f"Bid must be higher than current price: {listing['current_price']}")

        # Check if bidder has enough credits
        if not deduct_credits(bidder_id, amount, db=db):
            raise ValueError("Insufficient credits")

        # Refund previous high bidder if exists
        previous_bid = db.execute(select(Bid).filter(Bid.listing_id == listing_id).order_by(desc(Bid.amount)).limit(1)).scalar_one_or_none()
        if previous_bid:
            add_credits(previous_bid.bidder_id, previous_bid.amount, db=db)

        # Create new bid
        bid_data = {
            'listing_id': listing_id,
            'bidder_id': bidder_id,
            'amount': amount,
            'created_at': datetime.utcnow()
        }
        bid_dict = bid_to_dict(bid_data)
        bid = Bid(**bid_dict)
        db.add(bid)
        db.commit()
        db.refresh(bid)

        # Update listing current price and bid count
        listing_obj = db.execute(select(Listing).filter(Listing.id == listing_id)).scalar_one()
        listing_obj.current_price = amount
        listing_obj.bid_count += 1
        listing_obj.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(listing_obj)

        bid_dict['id'] = bid.id
        return bid_dict

    except Exception as e:
        logger.error(f"Error creating bid: {e}")
        raise

def get_listing_bids(listing_id: int, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Get all bids for a listing."""
    bids = db.execute(select(Bid).filter(Bid.listing_id == listing_id).order_by(desc(Bid.amount))).scalars().all()
    result = []
    for bid in bids:
        bid_data = bid.__dict__
        # Get bidder details
        bidder = get_user(bid_data['bidder_id'], db=db)
        if bidder:
            bid_data['bidder'] = {
                'id': bid_data['bidder_id'],
                'display_name': bidder.get('display_name')
            }
        result.append(bid_data)
    return result

def finalize_auction(listing_id: int, db: Session = next(get_db())) -> Dict[str, Any]:
    """Finalize an auction when it expires."""
    try:
        from firestore_db_ops.listing_ops import get_listing
        listing = get_listing(listing_id, db=db)
        if not listing:
            raise ValueError("Listing not found")

        if listing['listing_type'] != ListingType.AUCTION.value:
            raise ValueError("Listing is not an auction")

        if listing['status'] != ListingStatus.OPEN.value:
            raise ValueError("Auction is not active")

        if datetime.utcnow() <= listing['expires_at']:
            raise ValueError("Auction has not ended yet")

        # Get winning bid
        winning_bid = db.execute(select(Bid).filter(Bid.listing_id == listing_id).order_by(desc(Bid.amount)).limit(1)).scalar_one_or_none()
        
        listing_obj = db.execute(select(Listing).filter(Listing.id == listing_id)).scalar_one()
        if winning_bid:
            # Update listing
            listing_obj.status = ListingStatus.SOLD
            listing_obj.buyer_id = winning_bid.bidder_id
            listing_obj.sold_at = datetime.utcnow()
            listing_obj.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(listing_obj)

            # Transfer card ownership
            card = db.execute(select(Card).filter(Card.id == listing['card_id'])).scalar_one()
            card.user_id = winning_bid.bidder_id
            db.commit()
            db.refresh(card)

            # Transfer credits to seller
            add_credits(listing['seller_id'], winning_bid.amount, db=db)
        else:
            # No bids, auction expires
            listing_obj.status = ListingStatus.EXPIRED
            listing_obj.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(listing_obj)

        return get_listing(listing_id, db=db)

    except Exception as e:
        logger.error(f"Error finalizing auction: {e}")
        raise