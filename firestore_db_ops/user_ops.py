from typing import Optional, Dict, Any
from firestore_db_ops.firestore_init import db, user_to_dict, logger

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