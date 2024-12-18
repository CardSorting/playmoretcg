import random
import json
import logging
from typing import Dict, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_random_exponential
from openai_config import openai_client
from cardgenerator.card_data_utils import standardize_card_data, validate_card_data, get_rarity
from cardgenerator.prompt_utils import generate_card_prompt, create_dalle_prompt
from cardgenerator.image_utils import generate_card_image
from models import Rarity

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_SET_NAME = 'GEN'
CARD_NUMBER_LIMIT = 999

def get_next_set_name_and_number() -> Tuple[str, int, int]:
    """Get the next set name, set number, and card number."""
    set_number = random.randint(1, 10)
    return DEFAULT_SET_NAME, set_number, random.randint(1, CARD_NUMBER_LIMIT)

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(5))
def generate_card(rarity: str = None) -> Dict[str, Any]:
    """Generate a card with optional rarity."""
    prompt = generate_card_prompt(rarity)
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            # Log that we're generating card data (not image)
            logger.info("Generating card data with GPT-4...")
            
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a Magic: The Gathering card designer. Create balanced and thematic cards that follow the game's rules and mechanics. Keep abilities clear and concise, using established keyword mechanics where possible. Limit flavor text to one or two impactful sentences."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            card_data_str = response.choices[0].message.content
            logger.debug(f"Raw card data from GPT (attempt {attempt + 1}): {card_data_str}")
            
            try:
                card_data = json.loads(card_data_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                if attempt < max_attempts - 1:
                    continue
                raise ValueError("Failed to generate valid card data after multiple attempts")
            
            # Get themed elements based on colors
            if 'color' in card_data:
                from cardgenerator.prompt_utils import get_themed_elements
                colors = card_data['color'] if isinstance(card_data['color'], list) else [card_data['color']]
                card_data['themes'] = get_themed_elements(colors)
            
            standardize_card_data(card_data)
            
            if not validate_card_data(card_data):
                if attempt < max_attempts - 1:
                    logger.warning(f"Invalid card data on attempt {attempt + 1}, retrying...")
                    continue
                raise ValueError("Failed to generate valid card data after multiple attempts")
            
            set_name, set_number, card_number = get_next_set_name_and_number()
            
            if not rarity:
                card_rarity = get_rarity(set_number, card_number)
                card_data['rarity'] = card_rarity.value
            
            card_data['set_name'] = set_name
            card_data['card_number'] = card_number
            
            try:
                # Log successful card data generation
                logger.info("Card data generated successfully")
                logger.debug(f"Final card data: {json.dumps(card_data, indent=2)}")
                
                # Try to generate the image
                dalle_url, b2_url = generate_card_image(card_data)
                
                # If we got here, both card data and image generation succeeded
                card_data['dalle_url'] = dalle_url
                card_data['b2_url'] = b2_url
                
                return card_data
                
            except Exception as img_error:
                logger.error(f"Error during image generation: {img_error}")
                if attempt < max_attempts - 1:
                    continue
                raise ValueError(f"Failed to generate card image after {max_attempts} attempts: {str(img_error)}")
                
        except Exception as e:
            logger.error(f"Error generating card data (attempt {attempt + 1}): {e}")
            if attempt < max_attempts - 1:
                continue
            raise ValueError(f"Failed to generate card after {max_attempts} attempts: {str(e)}")