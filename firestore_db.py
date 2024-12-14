from firebase_admin import firestore, credentials, initialize_app
from datetime import datetime
from typing import Optional, Dict, Any, List
import random
import logging
from models import Rarity

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
        'last_login': datetime.utcnow()
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
            
        # Randomly select the requested number of cards
        selected = random.sample(cards, min(count, len(cards)))
        return [{**doc.to_dict(), 'id': doc.id} for doc in selected]
        
    except Exception as e:
        logger.error(f"Error getting random {rarity} cards: {e}")
        raise

def claim_card(card_id: str, user_id: str) -> Dict[str, Any]:
    """Claim a card for a user."""
    try:
        card_ref = db.collection('cards').document(card_id)
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

def open_pack(user_id: str) -> List[Dict[str, Any]]:
    """Open a pack of cards for a user."""
    try:
        pack_cards = []
        claimed_ids = []
        
        # Get one rare/mythic rare card (15% chance of mythic)
        is_mythic = random.random() < 0.15
        rarity = Rarity.MYTHIC_RARE.value if is_mythic else Rarity.RARE.value
        rare_cards = get_random_cards_by_rarity(rarity, 1)
        for card in rare_cards:
            claimed = claim_card(card['id'], user_id)
            pack_cards.append(claimed)
            claimed_ids.append(card['id'])
        
        # Get three uncommon cards
        uncommon_cards = get_random_cards_by_rarity(Rarity.UNCOMMON.value, 3, claimed_ids)
        for card in uncommon_cards:
            claimed = claim_card(card['id'], user_id)
            pack_cards.append(claimed)
            claimed_ids.append(card['id'])
        
        # Get six common cards
        common_cards = get_random_cards_by_rarity(Rarity.COMMON.value, 6, claimed_ids)
        for card in common_cards:
            claimed = claim_card(card['id'], user_id)
            pack_cards.append(claimed)
            claimed_ids.append(card['id'])
        
        # Sort cards by rarity
        return sorted(
            pack_cards,
            key=lambda x: [Rarity.MYTHIC_RARE.value, Rarity.RARE.value, Rarity.UNCOMMON.value, Rarity.COMMON.value].index(x['rarity'])
        )
        
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