import asyncio
import logging
from typing import List, Dict, Any
from card_generator import generate_card, generate_card_image
import firestore_db
from models import Rarity

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
CARDS_PER_RARITY = {
    Rarity.COMMON: 100,     # 100 common cards
    Rarity.UNCOMMON: 60,    # 60 uncommon cards
    Rarity.RARE: 30,        # 30 rare cards
    Rarity.MYTHIC_RARE: 10  # 10 mythic rare cards
}

ADMIN_USER_ID = "system"  # System user ID for generated cards

async def generate_cards_for_rarity(rarity: Rarity, count: int) -> List[Dict[str, Any]]:
    """Generate a specified number of cards for a given rarity."""
    cards = []
    for i in range(count):
        try:
            logger.info(f"Generating {rarity.value} card {i+1}/{count}")
            
            # Generate card data
            card_data = generate_card(rarity.value)
            card_data['user_id'] = ADMIN_USER_ID
            
            # Generate and upload image
            image_url, b2_url = generate_card_image(card_data)
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            
            # Create card in Firestore
            card = firestore_db.create_card(card_data, b2_url, filename)
            cards.append(card)
            
            logger.info(f"Successfully created {rarity.value} card: {card['name']}")
            
        except Exception as e:
            logger.error(f"Error generating {rarity.value} card: {e}")
            continue
            
        # Small delay between generations to avoid rate limits
        await asyncio.sleep(1)
    
    return cards

async def seed_database():
    """Generate all cards for the database."""
    total_cards = []
    
    for rarity, count in CARDS_PER_RARITY.items():
        logger.info(f"Starting generation of {count} {rarity.value} cards")
        cards = await generate_cards_for_rarity(rarity, count)
        total_cards.extend(cards)
        logger.info(f"Completed generation of {len(cards)} {rarity.value} cards")
    
    logger.info(f"Database seeding complete. Generated {len(total_cards)} total cards")
    return total_cards

if __name__ == "__main__":
    logger.info("Starting database seeding")
    asyncio.run(seed_database())