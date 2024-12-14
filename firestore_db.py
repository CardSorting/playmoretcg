from firebase_admin import firestore, credentials, initialize_app
from datetime import datetime
from typing import Optional, Dict, Any, List
import enum
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK if not already initialized
cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
if not cred_path:
    raise ValueError("FIREBASE_CREDENTIALS_PATH environment variable is not set")

try:
    cred = credentials.Certificate(cred_path)
    initialize_app(cred)
except ValueError:
    # App already initialized
    pass

# Initialize Firestore client
db = firestore.client()

class Rarity(enum.Enum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    MYTHIC_RARE = "Mythic Rare"

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
    # Convert rarity enum to string if present
    rarity = card_data.get('rarity')
    if isinstance(rarity, Rarity):
        rarity = rarity.value
    elif isinstance(rarity, str):
        rarity = Rarity[rarity.upper().replace(' ', '_')].value

    return {
        'name': card_data.get('name'),
        'manaCost': card_data.get('manaCost'),
        'type': card_data.get('type'),
        'color': card_data.get('color'),
        'abilities': card_data.get('abilities'),
        'flavorText': card_data.get('flavorText'),
        'rarity': rarity,
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

def delete_card(card_id: str, user_id: str) -> bool:
    """Delete a card."""
    card_ref = db.collection('cards').document(card_id)
    card = card_ref.get()
    
    if card.exists and card.to_dict().get('user_id') == user_id:
        card_ref.delete()
        return True
    return False

def get_random_cards(limit: int = 6) -> List[Dict[str, Any]]:
    """Get random cards."""
    # Note: Firestore doesn't support random queries directly
    # This is a simple implementation that gets all cards and randomly selects from them
    # For production, consider implementing a more efficient solution
    cards = list(db.collection('cards').stream())
    
    import random
    selected = random.sample(cards, min(limit, len(cards)))
    
    return [{**doc.to_dict(), 'id': doc.id} for doc in selected]

# Migration function
def migrate_from_sqlite(sqlite_session):
    """Migrate data from SQLite to Firestore."""
    from models import User, Card, CardImage
    
    # Migrate users
    users = sqlite_session.query(User).all()
    for user in users:
        user_data = {
            'email': user.email,
            'display_name': user.display_name,
            'created_at': user.created_at,
            'last_login': user.last_login
        }
        create_user(user.id, user_data)
    
    # Migrate cards
    cards = sqlite_session.query(Card).all()
    for card in cards:
        card_data = {
            'name': card.name,
            'manaCost': card.manaCost,
            'type': card.type,
            'color': card.color,
            'abilities': card.abilities,
            'flavorText': card.flavorText,
            'rarity': card.rarity.value,
            'set_name': card.set_name,
            'card_number': card.card_number,
            'created_at': card.created_at,
            'user_id': card.user_id,
            'images': [{
                'backblaze_url': image.backblaze_url,
                'filename': image.filename,
                'created_at': image.created_at
            } for image in card.images]
        }
        create_card(card_data)