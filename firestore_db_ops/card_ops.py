from typing import Optional, Dict, Any, List
from datetime import datetime
import random
from firestore_db_ops.firestore_init import db, card_to_dict, logger
from models import Rarity
from google.api_core import exceptions
from firebase_admin import firestore

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

def _select_random_cards_by_rarity(rarity: str, count: int, exclude_ids: List[str] = None) -> List[Dict[str, Any]]:
    """Select random unclaimed cards of a specific rarity."""
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

def _claim_card_helper(card_id: str, user_id: str) -> Dict[str, Any]:
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
        
def claim_card(card_id: str, user_id: str, transaction=None) -> Dict[str, Any]:
    """Claim a card for a user."""
    try:
        if transaction:
            card_ref = db.collection('cards').document(card_id)
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
            return _claim_card_helper(card_id, user_id)
    except Exception as e:
        logger.error(f"Error claiming card {card_id} for user {user_id}: {e}")
        raise

def open_pack(user_id: str, pack_cost: int = 50) -> List[Dict[str, Any]]:
    """Open a pack of cards for a user using a transaction."""
    logger.info(f"Opening pack for user: {user_id}")
    try:
        # Select cards outside of the transaction
        pack_cards = []
        claimed_ids = []
    
        # Get one rare/mythic rare card (15% chance of mythic)
        is_mythic = random.random() < 0.15
        rarity = Rarity.MYTHIC_RARE.value if is_mythic else Rarity.RARE.value
        logger.info(f"Getting random card of rarity: {rarity}")
        rare_cards = _select_random_cards_by_rarity(rarity, 1, exclude_ids=claimed_ids)
        logger.info(f"Got rare cards: {[card['id'] for card in rare_cards]}")
        pack_cards.extend(rare_cards)
        claimed_ids.extend([card['id'] for card in rare_cards])
    
        # Get three uncommon cards
        logger.info(f"Getting 3 random cards of rarity: {Rarity.UNCOMMON.value}")
        uncommon_cards = _select_random_cards_by_rarity(Rarity.UNCOMMON.value, 3, exclude_ids=claimed_ids)
        logger.info(f"Got uncommon cards: {[card['id'] for card in uncommon_cards]}")
        pack_cards.extend(uncommon_cards)
        claimed_ids.extend([card['id'] for card in uncommon_cards])
    
        # Get six common cards
        logger.info(f"Getting 6 random cards of rarity: {Rarity.COMMON.value}")
        common_cards = _select_random_cards_by_rarity(Rarity.COMMON.value, 6, exclude_ids=claimed_ids)
        logger.info(f"Got common cards: {[card['id'] for card in common_cards]}")
        pack_cards.extend(common_cards)
        claimed_ids.extend([card['id'] for card in common_cards])
    
        def open_pack_transaction(transaction):
            logger.info(f"Deducting {pack_cost} credits from user {user_id}")
            from firestore_db_ops.user_ops import deduct_credits
            if not deduct_credits(user_id, pack_cost, transaction=transaction):
                logger.error(f"Insufficient credits for user {user_id}. Pack costs {pack_cost} credits.")
                raise ValueError(f"Insufficient credits. Pack costs {pack_cost} credits.")
            logger.info(f"Successfully deducted {pack_cost} credits from user {user_id}")
    
            claimed_cards = []
            for card in pack_cards:
                logger.info(f"Claiming card {card['id']} for user {user_id}")
                claimed = claim_card(card['id'], user_id, transaction=transaction)
                logger.info(f"Successfully claimed card {card['id']} for user {user_id}")
                claimed_cards.append(claimed)
    
            # Sort cards by rarity
            return sorted(
                claimed_cards,
                key=lambda x: [Rarity.MYTHIC_RARE.value, Rarity.RARE.value, Rarity.UNCOMMON.value, Rarity.COMMON.value].index(x['rarity'])
            )
        
        logger.info(f"Running transaction for user {user_id}")
        result = db.run_in_transaction(open_pack_transaction)
        logger.info(f"Transaction completed successfully for user {user_id}")
        return result
    except ValueError as ve:
        logger.error(f"ValueError opening pack for user {user_id}: {ve}")
        raise
    except exceptions.GoogleAPIError as fe:
        logger.error(f"FirestoreError opening pack for user {user_id}: {fe}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error opening pack for user {user_id}: {e}")
        raise

def delete_card(card_id: str, user_id: str) -> bool:
    """Delete a card."""
    card_ref = db.collection('cards').document(card_id)
    card = card_ref.get()
    
    if card.exists and card.to_dict().get('user_id') == user_id:
        card_ref.delete()
        return True
    return False