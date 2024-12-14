import random
import json
import logging
import requests
import io
from typing import Dict, Any, List, Tuple
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_random_exponential
from openai_config import openai_client
from backblaze_config import upload_image
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
DEFAULT_RARITY_PROBABILITIES = {
    Rarity.COMMON: 0.60,
    Rarity.UNCOMMON: 0.30,
    Rarity.RARE: 0.08,
    Rarity.MYTHIC_RARE: 0.02
}

def safe_get_dict(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get a value from a dictionary, providing a default if the key is missing."""
    return data.get(key, default)

def standardize_card_data(card_data: Dict[str, Any]) -> None:
    """Standardizes card data fields and ensures all required fields are present."""
    mapping = {
        'Name': 'name',
        'ManaCost': 'manaCost',
        'Type': 'type',
        'Color': 'color',
        'Abilities': 'abilities',
        'FlavorText': 'flavorText',
        'Rarity': 'rarity',
        'PowerToughness': 'powerToughness'
    }

    # Transfer uppercase values to lowercase fields if present
    for old_key, new_key in mapping.items():
        if old_key in card_data:
            card_data[new_key] = card_data.pop(old_key)

    # Validate required fields
    required_fields = ['name', 'manaCost', 'type', 'color', 'abilities', 'flavorText', 'rarity']
    for field in required_fields:
        if field not in card_data or not card_data[field]:
            card_data[field] = get_default_value_for_field(field)

    # Convert rarity string to enum
    if isinstance(card_data['rarity'], str):
        card_data['rarity'] = Rarity[card_data['rarity'].upper().replace(' ', '_')]

    # Convert rarity enum to string value for Firestore
    if isinstance(card_data['rarity'], Rarity):
        card_data['rarity'] = card_data['rarity'].value

def get_default_value_for_field(field: str) -> Any:
    """Provide default values for missing card fields."""
    default_values = {
        'name': 'Unnamed Card',
        'manaCost': '{0}',
        'type': 'Unknown Type',
        'color': 'Colorless',
        'abilities': 'No abilities',
        'flavorText': 'No flavor text',
        'rarity': Rarity.COMMON.value,  # Return string value instead of enum
        'powerToughness': 'N/A'
    }
    return default_values.get(field, 'Unknown')

def get_next_set_name_and_number() -> Tuple[str, int]:
    """Get the next set name and card number."""
    return DEFAULT_SET_NAME, random.randint(1, CARD_NUMBER_LIMIT)

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def generate_card(rarity: str = None) -> Dict[str, Any]:
    """Generate a card with optional rarity."""
    # If rarity is "Rare", randomly decide if it should be Mythic Rare
    if rarity == "Rare":
        probabilities = get_rarity_probabilities()
        mythic_chance = probabilities[Rarity.MYTHIC_RARE] / (probabilities[Rarity.RARE] + probabilities[Rarity.MYTHIC_RARE])
        if random.random() < mythic_chance:
            rarity = "Mythic Rare"

    prompt = generate_card_prompt(rarity)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        card_data_str = response.choices[0].message.content
        logger.debug(f"Raw card data from GPT: {card_data_str}")
        card_data = json.loads(card_data_str)

        standardize_card_data(card_data)
        set_name, card_number = get_next_set_name_and_number()
        card_data['set_name'] = set_name
        card_data['card_number'] = card_number

        return card_data

    except Exception as e:
        logger.error(f"Error generating card: {e}")
        return generate_fallback_card(rarity)

def generate_card_prompt(rarity: str = None) -> str:
    """Generate the GPT prompt for creating the card."""
    rarity_options = ', '.join([r.value for r in Rarity])
    return (
        f"Create a unique Magic: The Gathering card with these attributes:\n"
        "- Name: A creative, thematic name\n"
        "- ManaCost: Using curly braces (e.g., {2}{W}{U})\n"
        "- Type: Full type line (e.g., 'Legendary Creature - Elf Warrior')\n"
        "- Color: White, Blue, Black, Red, Green, or Colorless\n"
        "- Abilities: List of abilities or rules text\n"
        "- PowerToughness: For creatures, e.g., '2/3', or null for non-creatures\n"
        "- FlavorText: A short, thematic description or quote\n"
        f"- Rarity: {rarity if rarity else rarity_options}\n"
        "Return the response as a JSON object."
    )

def generate_fallback_card(rarity: str) -> Dict[str, Any]:
    """Generate a basic fallback card when GPT response is invalid."""
    rarity_enum = Rarity.COMMON if not rarity else Rarity[rarity.upper().replace(' ', '_')]
    return {
        'name': 'Default Card',
        'manaCost': '{0}',
        'type': 'Basic Creature - Placeholder',
        'color': 'Colorless',
        'abilities': 'None',
        'flavorText': 'Default fallback card.',
        'rarity': rarity_enum.value,  # Convert enum to string value
        'set_name': DEFAULT_SET_NAME,
        'card_number': 1
    }

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def generate_card_image(card_data: Dict[str, Any]) -> Tuple[str, str]:
    """Generate artwork for the card using OpenAI's image generation API."""
    prompt = generate_image_prompt(card_data)

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        
        image_url = response.data[0].url
        
        # Download image from OpenAI
        response = requests.get(image_url)
        if response.status_code != 200:
            raise ValueError(f"Failed to download image: Status {response.status_code}")
        
        # Prepare image data for upload
        image_data = response.content
        filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
        
        # Upload to Backblaze
        b2_url = upload_image(image_data, filename)
        
        return image_url, b2_url

    except Exception as e:
        logger.error(f"Error generating card image: {e}")
        raise ValueError(f"Failed to generate card image: {e}")

def generate_image_prompt(card_data: Dict[str, Any]) -> str:
    """Generate an image generation prompt based on card type and attributes."""
    card_type = card_data.get('type', 'Unknown')

    prompt = f"Create fantasy artwork for {card_data.get('name')}. "

    if 'Creature' in card_type:
        prompt += f"Show a {card_type.lower()} in action. "
    elif 'Enchantment' in card_type:
        prompt += "Depict a magical aura or mystical effect. "
    elif 'Artifact' in card_type:
        prompt += "Illustrate a detailed magical item or relic. "
    elif 'Land' in card_type:
        prompt += f"Illustrate a landscape for {card_data['name']}. "
    elif 'Planeswalker' in card_type:
        prompt += f"Show a powerful {card_type.lower()} character. "
    else:
        prompt += "Depict the card's effect in a visually appealing way. "

    # Handle rarity being either string or enum
    rarity = card_data['rarity']
    if isinstance(rarity, Rarity):
        rarity = rarity.value

    prompt += f"Use the {card_data['color']} color scheme with {rarity.lower()} quality. "
    prompt += "High detail, dramatic lighting, no text or borders."

    return prompt

def get_rarity_probabilities() -> Dict[Rarity, float]:
    """Get the rarity probabilities."""
    return DEFAULT_RARITY_PROBABILITIES