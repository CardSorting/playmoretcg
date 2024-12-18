from typing import Optional, Dict, Any, List
from datetime import datetime
import random
from db_ops.firestore_init import get_db, card_to_dict, logger, Card, User
from models import Rarity
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import NoResultFound

def create_card(card_data: Dict[str, Any], image_url: Optional[str] = None, filename: Optional[str] = None, db: Session = next(get_db())) -> Dict[str, Any]:
    """Create a new card."""
    if image_url and filename:
        card_data['images'] = f"{image_url},{filename}"
    card_dict = card_to_dict(card_data)
    card = Card(**card_dict)
    db.add(card)
    db.commit()
    db.refresh(card)
    card_dict['id'] = card.id
    return card_dict

def get_card(card_id: int, db: Session = next(get_db())) -> Optional[Dict[str, Any]]:
    """Get card by ID."""
    card = db.execute(select(Card).filter(Card.id == card_id)).scalar_one_or_none()
    return card.__dict__ if card else None

def get_user_cards(user_id: int, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Get all cards for a user."""
    cards = db.execute(select(Card).filter(Card.user_id == user_id)).scalars().all()
    return [card.__dict__ for card in cards]

def get_random_cards(limit: int = 6, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Get random cards."""
    cards = db.execute(select(Card).order_by(func.random()).limit(limit)).scalars().all()
    return [card.__dict__ for card in cards]

def get_random_cards_by_rarity(rarity: str, count: int = 1, exclude_ids: List[int] = None, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Get random unclaimed cards of a specific rarity."""
    try:
        query = select(Card).filter(Card.rarity == rarity, Card.user_id == None)
        if exclude_ids:
            query = query.filter(Card.id.notin_(exclude_ids))
        cards = db.execute(query.order_by(func.random()).limit(count)).scalars().all()
        if not cards:
            raise ValueError(f"No available {rarity} cards")
        return [card.__dict__ for card in cards]
    except Exception as e:
        logger.error(f"Error getting random {rarity} cards: {e}")
        raise

def _select_random_cards_by_rarity(rarity: str, count: int, exclude_ids: List[int] = None, db: Session = next(get_db())) -> List[Dict[str, Any]]:
    """Select random unclaimed cards of a specific rarity."""
    try:
        query = select(Card).filter(Card.rarity == rarity, Card.user_id == None)
        if exclude_ids:
            query = query.filter(Card.id.notin_(exclude_ids))
        cards = db.execute(query.order_by(func.random()).limit(count)).scalars().all()
        if not cards:
            raise ValueError(f"No available {rarity} cards")
        return [card.__dict__ for card in cards]
    except Exception as e:
        logger.error(f"Error getting random {rarity} cards: {e}")
        raise

def _claim_card_helper(card_id: int, user_id: int, db: Session = next(get_db())) -> Dict[str, Any]:
    """Claim a card for a user."""
    try:
        card = db.execute(select(Card).filter(Card.id == card_id)).scalar_one()
        if card.user_id is not None:
            raise ValueError(f"Card {card_id} is already claimed")
        card.user_id = user_id
        db.commit()
        db.refresh(card)
        return card.__dict__
    except NoResultFound:
         raise ValueError(f"Card {card_id} not found")
    except Exception as e:
        logger.error(f"Error claiming card {card_id} for user {user_id}: {e}")
        raise

def claim_card(card_id: int, user_id: int, db: Session = next(get_db())) -> Dict[str, Any]:
    """Claim a card for a user."""
    try:
        return _claim_card_helper(card_id, user_id, db)
    except Exception as e:
        logger.error(f"Error claiming card {card_id} for user {user_id}: {e}")
        raise

def open_pack(user_id: int, pack_cost: int = 50, db: Session = next(get_db())) -> List[Dict[str, Any]]:
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
        rare_cards = _select_random_cards_by_rarity(rarity, 1, exclude_ids=claimed_ids, db=db)
        logger.info(f"Got rare cards: {[card['id'] for card in rare_cards]}")
        pack_cards.extend(rare_cards)
        claimed_ids.extend([card['id'] for card in rare_cards])

        # Get three uncommon cards
        logger.info(f"Getting 3 random cards of rarity: {Rarity.UNCOMMON.value}")
        uncommon_cards = _select_random_cards_by_rarity(Rarity.UNCOMMON.value, 3, exclude_ids=claimed_ids, db=db)
        logger.info(f"Got uncommon cards: {[card['id'] for card in uncommon_cards]}")
        pack_cards.extend(uncommon_cards)
        claimed_ids.extend([card['id'] for card in uncommon_cards])

        # Get six common cards
        logger.info(f"Getting 6 random cards of rarity: {Rarity.COMMON.value}")
        common_cards = _select_random_cards_by_rarity(Rarity.COMMON.value, 6, exclude_ids=claimed_ids, db=db)
        logger.info(f"Got common cards: {[card['id'] for card in common_cards]}")
        pack_cards.extend(common_cards)
        claimed_ids.extend([card['id'] for card in common_cards])

        from db_ops.user_ops import deduct_credits
        if not deduct_credits(user_id, pack_cost, db=db):
            logger.error(f"Insufficient credits for user {user_id}. Pack costs {pack_cost} credits.")
            raise ValueError(f"Insufficient credits. Pack costs {pack_cost} credits.")
        logger.info(f"Successfully deducted {pack_cost} credits from user {user_id}")

        claimed_cards = []
        for card in pack_cards:
            logger.info(f"Claiming card {card['id']} for user {user_id}")
            claimed = claim_card(card['id'], user_id, db=db)
            logger.info(f"Successfully claimed card {card['id']} for user {user_id}")
            claimed_cards.append(claimed)

        # Sort cards by rarity
        return sorted(
            claimed_cards,
            key=lambda x: [Rarity.MYTHIC_RARE.value, Rarity.RARE.value, Rarity.UNCOMMON.value, Rarity.COMMON.value].index(x['rarity'])
        )
    except ValueError as ve:
        logger.error(f"ValueError opening pack for user {user_id}: {ve}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error opening pack for user {user_id}: {e}")
        raise

def delete_card(card_id: int, user_id: int, db: Session = next(get_db())) -> bool:
    """Delete a card."""
    card = db.execute(select(Card).filter(Card.id == card_id)).scalar_one_or_none()
    if card and card.user_id == user_id:
        db.delete(card)
        db.commit()
        return True
    return False