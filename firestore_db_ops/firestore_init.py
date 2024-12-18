from firebase_admin import firestore, credentials, initialize_app
from datetime import datetime
from typing import Dict, Any
import logging

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