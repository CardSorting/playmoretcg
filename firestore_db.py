from firebase_admin import firestore, credentials, initialize_app
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import random
import logging
from models import Rarity, ListingStatus, ListingType, ListingDuration

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate('cred/playmoretcg-774b1-firebase-adminsdk-dnfs3-c0010bde40.json')
    initialize_app(cred)
except ValueError:
    # App already initialized
    pass

# Initialize Firestore client
db = firestore.client()

def user_to_dict(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert user data to Firestore format."""
    return {
        'email': user_data.get('email'),
        'display_name': user_data.get('display_name'),
        'created_at': user_data.get('created_at', datetime.utcnow()),
        'last_login': datetime.utcnow(),
        'credits': user_data.get('credits', 100)  # Default 100 credits for new users
    }

def card_to_dict(card_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert card data to Firestore format."""
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
    """Convert bid data to Firestore format."""
    return {
        'listing_id': bid_data.get('listing_id'),
        'bidder_id': bid_data.get('bidder_id'),
        'amount': bid_data.get('amount'),
        'created_at': bid_data.get('created_at', datetime.utcnow())
    }

def listing_to_dict(listing_data: Dict[str, Any], include_bids: bool = False) -> Dict[str, Any]:
    """Convert listing data to Firestore format."""
    now = datetime.utcnow()
    duration = listing_data.get('duration', ListingDuration.ONE_DAY.value)
    expires_at = listing_data.get('expires_at', now + ListingDuration.get_timedelta(ListingDuration(duration)))
    
    listing_dict = {
        'card_id': listing_data.get('card_id'),
        'seller_id': listing_data.get('seller_id'),
        'buyer_id': listing_data.get('buyer_id'),
        'listing_type': listing_data.get('listing_type', ListingType.FIXED_PRICE.value),
        'price': listing_data.get('price'),
        'current_price': listing_data.get('current_price', listing_data.get('price')),
        'status': listing_data.get('status', ListingStatus.ACTIVE.value),
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

# Bid Operations
def create_bid(listing_id: str, bidder_id: str, amount: float) -> Dict[str, Any]:
    """Create a new bid for an auction listing."""
    try:
        # Get listing
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

# Marketplace Operations
def create_listing(card_id: str, seller_id: str, price: float, duration: str, listing_type: str = ListingType.FIXED_PRICE.value) -> Dict[str, Any]:
    """Create a new listing for a card."""
    try:
        # Check if card exists and belongs to seller
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

# Credit Operations
def get_user_credits(user_id: str) -> int:
    """Get user's current credit balance."""
    user = get_user(user_id)
    return user.get('credits', 0) if user else 0

def add_credits(user_id: str, amount: int) -> int:
    """Add credits to user's balance."""
    user_ref = db.collection('users').document(user_id)
    current_credits = get_user_credits(user_id)
    new_balance = current_credits + amount
    user_ref.update({'credits': new_balance})
    return new_balance

def deduct_credits(user_id: str, amount: int, transaction=None) -> bool:
    """Deduct credits from user's balance if sufficient funds exist."""
    user_ref = db.collection('users').document(user_id)
    
    if transaction:
        user_doc = transaction.get(user_ref)
        if not user_doc.exists:
            return False
        current_credits = user_doc.to_dict().get('credits', 0)
        if current_credits >= amount:
            new_balance = current_credits - amount
            transaction.update(user_ref, {'credits': new_balance})
            return True
        return False
    else:
        current_credits = get_user_credits(user_id)
        if current_credits >= amount:
            new_balance = current_credits - amount
            user_ref.update({'credits': new_balance})
            return True
        return False

# User Operations
def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    doc = db.collection('users').document(user_id).get()
    return doc.to_dict() if doc.exists else None

def create_user(user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new user."""
    user_ref = db.collection('users').document(user_id)
    user_dict = user_to_dict(user_data)
    user_ref.set(user_dict)
    return user_dict

def update_user(user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update user data."""
    user_ref = db.collection('users').document(user_id)
    user_dict = user_to_dict(user_data)
    user_ref.update(user_dict)
    return user_dict

def delete_user(user_id: str) -> bool:
    """Delete user and all their cards."""
    batch = db.batch()
    
    # Delete user document
    user_ref = db.collection('users').document(user_id)
    batch.delete(user_ref)
    
    # Delete all user's cards
    cards = db.collection('cards').where('user_id', '==', user_id).stream()
    for card in cards:
        batch.delete(card.reference)
    
    batch.commit()
    return True

# Card Operations
def create_card(card_data: Dict[str, Any], image_url: Optional[str] = None, filename: Optional[str] = None) -> Dict[str, Any]:
    """Create a new card."""
    if image_url and filename:
        card_data['images'] = [{
            'backblaze_url': image_url,
            'filename': filename,
            'created_at': datetime.utcnow()
        }]
    
    card_ref = db.collection('cards').document()
    card_dict = card_to_dict(card_data)
    card_ref.set(card_dict)
    
    # Add ID to the returned dictionary
    card_dict['id'] = card_ref.id
    return card_dict

def get_card(card_id: str) -> Optional[Dict[str, Any]]:
    """Get card by ID."""
    doc = db.collection('cards').document(card_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None

def get_user_cards(user_id: str) -> List[Dict[str, Any]]:
    """Get all cards for a user."""
    cards = []
    for doc in db.collection('cards').where('user_id', '==', user_id).stream():
        card_data = doc.to_dict()
        card_data['id'] = doc.id
        cards.append(card_data)
    return cards

def get_random_cards(limit: int = 6) -> List[Dict[str, Any]]:
    """Get random cards."""
    cards = list(db.collection('cards').stream())
    selected = random.sample(cards, min(limit, len(cards)))
    return [{**doc.to_dict(), 'id': doc.id} for doc in selected]

def get_random_cards_by_rarity(rarity: str, count: int = 1, exclude_ids: List[str] = None) -> List[Dict[str, Any]]:
    """Get random unclaimed cards of a specific rarity."""
    try:
        # Get all unclaimed cards of the specified rarity
        query = db.collection('cards').where('rarity', '==', rarity).where('user_id', '==', 'system')
        
        if exclude_ids:
            # Exclude already selected cards
            query = query.where(firestore.FieldPath.document_id(), 'not-in', exclude_ids)
        
        cards = list(query.stream())
        
        if not cards:
            raise ValueError(f"No available {rarity} cards")
        
        selected_cards = []
        available_cards = cards.copy()
        
        for _ in range(count):
            if not available_cards:
                break # No more unique cards available
            
            selected = random.choice(available_cards)
            selected_cards.append({**selected.to_dict(), 'id': selected.id})
            available_cards.remove(selected)
            
        return selected_cards
        
    except Exception as e:
        logger.error(f"Error getting random {rarity} cards: {e}")
        raise

def claim_card(card_id: str, user_id: str, transaction=None) -> Dict[str, Any]:
    """Claim a card for a user."""
    try:
        card_ref = db.collection('cards').document(card_id)
        
        if transaction:
            card = transaction.get(card_ref)
            if not card.exists:
                raise ValueError(f"Card {card_id} not found")
            card_data = card.to_dict()
            if card_data['user_id'] != 'system':
                raise ValueError(f"Card {card_id} is already claimed")
            transaction.update(card_ref, {
                'user_id': user_id,
                'claimed_at': datetime.utcnow()
            })
            result = card.to_dict()
            result['id'] = card_id
            return result
        else:
            card = card_ref.get()
            if not card.exists:
                raise ValueError(f"Card {card_id} not found")
            card_data = card.to_dict()
            if card_data['user_id'] != 'system':
                raise ValueError(f"Card {card_id} is already claimed")
            # Update the card with the new user_id
            card_ref.update({
                'user_id': user_id,
                'claimed_at': datetime.utcnow()
            })
            # Get the updated card
            updated_card = card_ref.get()
            result = updated_card.to_dict()
            result['id'] = card_id
            return result
        
    except Exception as e:
        logger.error(f"Error claiming card {card_id} for user {user_id}: {e}")
        raise

def open_pack(user_id: str, pack_cost: int = 50) -> List[Dict[str, Any]]:
    """Open a pack of cards for a user using a transaction."""
    try:
        def open_pack_transaction(transaction):
            # Check if user has enough credits
            if not deduct_credits(user_id, pack_cost, transaction=transaction):
                raise ValueError(f"Insufficient credits. Pack costs {pack_cost} credits.")

            pack_cards = []
            claimed_ids = []

            # Get one rare/mythic rare card (15% chance of mythic)
            is_mythic = random.random() < 0.15
            rarity = Rarity.MYTHIC_RARE.value if is_mythic else Rarity.RARE.value
            rare_cards = get_random_cards_by_rarity(rarity, 1, exclude_ids=claimed_ids)
            for card in rare_cards:
                claimed = claim_card(card['id'], user_id, transaction=transaction)
                pack_cards.append(claimed)
                claimed_ids.append(card['id'])

            # Get three uncommon cards
            uncommon_cards = get_random_cards_by_rarity(Rarity.UNCOMMON.value, 3, exclude_ids=claimed_ids)
            for card in uncommon_cards:
                claimed = claim_card(card['id'], user_id, transaction=transaction)
                pack_cards.append(claimed)
                claimed_ids.append(card['id'])

            # Get six common cards
            common_cards = get_random_cards_by_rarity(Rarity.COMMON.value, 6, exclude_ids=claimed_ids)
            for card in common_cards:
                claimed = claim_card(card['id'], user_id, transaction=transaction)
                pack_cards.append(claimed)
                claimed_ids.append(card['id'])

            # Sort cards by rarity
            return sorted(
                pack_cards,
                key=lambda x: [Rarity.MYTHIC_RARE.value, Rarity.RARE.value, Rarity.UNCOMMON.value, Rarity.COMMON.value].index(x['rarity'])
            )

        # Run the transaction
        return db.run_in_transaction(open_pack_transaction)
    except Exception as e:
        logger.error(f"Error opening pack for user {user_id}: {e}")
        raise

def delete_card(card_id: str, user_id: str) -> bool:
    """Delete a card."""
    card_ref = db.collection('cards').document(card_id)
    card = card_ref.get()
    
    if card.exists and card.to_dict().get('user_id') == user_id:
        card_ref.delete()
        return True
    return False