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
BASE_RARITY_PROBABILITIES = {
    Rarity.COMMON: 0.60,
    Rarity.UNCOMMON: 0.30,
    Rarity.RARE: 0.08,
    Rarity.MYTHIC_RARE: 0.02
}

# Color combinations
MONO_COLORS = ['White', 'Blue', 'Black', 'Red', 'Green']
GUILD_COLORS = [
    ('White', 'Blue'), ('Blue', 'Black'), ('Black', 'Red'), ('Red', 'Green'),
    ('Green', 'White'), ('White', 'Black'), ('Blue', 'Red'), ('Black', 'Green'),
    ('Red', 'White'), ('Green', 'Blue')
]
SHARD_COLORS = [
    ('White', 'Blue', 'Black'), ('Blue', 'Black', 'Red'), ('Black', 'Red', 'Green'),
    ('Red', 'Green', 'White'), ('Green', 'White', 'Blue')
]

# Seasonal themes
SEASONAL_THEMES = {
    'spring': {
        'creatures': ['Druid', 'Elf', 'Beast', 'Bird', 'Unicorn'],
        'keywords': ['Growth', 'Bloom', 'Flourish', 'Renew'],
        'colors': ['Green', 'White']
    },
    'summer': {
        'creatures': ['Phoenix', 'Dragon', 'Elemental', 'Warrior', 'Djinn'],
        'keywords': ['Blaze', 'Fury', 'Scorch', 'Ignite'],
        'colors': ['Red', 'Green']
    },
    'fall': {
        'creatures': ['Vampire', 'Zombie', 'Wraith', 'Skeleton', 'Spirit'],
        'keywords': ['Decay', 'Wither', 'Harvest', 'Haunt'],
        'colors': ['Black', 'Red']
    },
    'winter': {
        'creatures': ['Wizard', 'Giant', 'Golem', 'Wolf', 'Construct'],
        'keywords': ['Frost', 'Chill', 'Hibernate', 'Freeze'],
        'colors': ['Blue', 'White']
    }
}

# Time of day themes
TIME_THEMES = {
    'morning': {
        'keywords': ['Dawn', 'Awaken', 'Rise', 'Illuminate'],
        'colors': ['White', 'Green']
    },
    'afternoon': {
        'keywords': ['Zenith', 'Radiate', 'Shine', 'Flourish'],
        'colors': ['Red', 'White']
    },
    'evening': {
        'keywords': ['Dusk', 'Twilight', 'Fade', 'Wane'],
        'colors': ['Blue', 'Black']
    },
    'night': {
        'keywords': ['Dark', 'Shadow', 'Moon', 'Dream'],
        'colors': ['Black', 'Blue']
    }
}

# Card type weights by rarity
TYPE_WEIGHTS = {
    Rarity.COMMON: {
        'Creature': 0.6,
        'Instant': 0.2,
        'Sorcery': 0.15,
        'Enchantment': 0.05
    },
    Rarity.UNCOMMON: {
        'Creature': 0.45,
        'Instant': 0.2,
        'Sorcery': 0.15,
        'Enchantment': 0.1,
        'Artifact': 0.1
    },
    Rarity.RARE: {
        'Creature': 0.35,
        'Instant': 0.15,
        'Sorcery': 0.15,
        'Enchantment': 0.15,
        'Artifact': 0.15,
        'Legendary Creature': 0.05
    },
    Rarity.MYTHIC_RARE: {
        'Legendary Creature': 0.3,
        'Planeswalker': 0.2,
        'Creature': 0.2,
        'Artifact': 0.15,
        'Enchantment': 0.15
    }
}

# Color combination weights by rarity
COLOR_WEIGHTS = {
    Rarity.COMMON: {'mono': 0.8, 'guild': 0.2},
    Rarity.UNCOMMON: {'mono': 0.6, 'guild': 0.4},
    Rarity.RARE: {'mono': 0.4, 'guild': 0.5, 'shard': 0.1},
    Rarity.MYTHIC_RARE: {'mono': 0.2, 'guild': 0.5, 'shard': 0.3}
}

def get_current_season() -> str:
    """Determine the current season based on the month."""
    month = datetime.now().month
    if 3 <= month <= 5:
        return 'spring'
    elif 6 <= month <= 8:
        return 'summer'
    elif 9 <= month <= 11:
        return 'fall'
    else:
        return 'winter'

def get_time_of_day() -> str:
    """Determine the time of day."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'

def get_color_combination(rarity: Rarity) -> List[str]:
    """Get a color combination based on rarity weights."""
    weights = COLOR_WEIGHTS[rarity]
    combo_type = random.choices(
        list(weights.keys()),
        weights=list(weights.values())
    )[0]
    
    if combo_type == 'mono':
        return [random.choice(MONO_COLORS)]
    elif combo_type == 'guild':
        return list(random.choice(GUILD_COLORS))
    else:  # shard
        return list(random.choice(SHARD_COLORS))

def get_card_type(rarity: Rarity) -> str:
    """Get a card type based on rarity weights."""
    weights = TYPE_WEIGHTS[rarity]
    return random.choices(
        list(weights.keys()),
        weights=list(weights.values())
    )[0]

def get_themed_elements() -> Dict[str, Any]:
    """Get themed elements based on current season and time."""
    season = get_current_season()
    time_of_day = get_time_of_day()
    
    elements = {
        'creatures': SEASONAL_THEMES[season]['creatures'],
        'keywords': (
            SEASONAL_THEMES[season]['keywords'] +
            TIME_THEMES[time_of_day]['keywords']
        ),
        'colors': list(set(
            SEASONAL_THEMES[season]['colors'] +
            TIME_THEMES[time_of_day]['colors']
        ))
    }
    
    return elements

def generate_card_prompt(rarity: str = None) -> str:
    """Generate the GPT prompt for creating the card."""
    if not rarity:
        rarity_options = ', '.join([r.value for r in Rarity])
        rarity_prompt = f"Choose from: {rarity_options}"
    else:
        rarity_prompt = rarity
        rarity_enum = Rarity[rarity.upper().replace(' ', '_')]
    
    # Get themed elements
    themes = get_themed_elements()
    
    # Get card type if rarity is specified
    card_type = get_card_type(rarity_enum) if rarity else "any appropriate type"
    
    # Get color combination if rarity is specified
    colors = get_color_combination(rarity_enum) if rarity else themes['colors']
    color_str = '/'.join(colors)
    
    # Build the prompt
    prompt = (
        f"Create a unique Magic: The Gathering card with these attributes:\n"
        f"- Name: A creative, thematic name incorporating seasonal or time-of-day elements\n"
        f"- ManaCost: Using curly braces (e.g., " + "{2}" + f"{color_str[0]}" + "), appropriate for the card's power level\n"
        f"- Type: {card_type}\n"
        f"- Color: {color_str}\n"
        "- Abilities: Create synergistic abilities that:\n"
        f"  * Use these themed keywords: {', '.join(random.sample(themes['keywords'], 2))}\n"
        "  * Match the card's colors and rarity\n"
        "  * Create interesting gameplay interactions\n"
        "- PowerToughness: For creatures, balanced for the mana cost\n"
        "- FlavorText: A thematic quote or description that fits the current "
        f"{get_current_season()} season and {get_time_of_day()} time of day\n"
        f"- Rarity: {rarity_prompt}\n"
        "Return the response as a JSON object."
    )
    
    return prompt

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
        'rarity': Rarity.COMMON.value,
        'powerToughness': 'N/A'
    }
    return default_values.get(field, 'Unknown')

def get_next_set_name_and_number() -> Tuple[str, int]:
    """Get the next set name and card number."""
    return DEFAULT_SET_NAME, random.randint(1, CARD_NUMBER_LIMIT)

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def generate_card(rarity: str = None) -> Dict[str, Any]:
    """Generate a card with optional rarity."""
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
        'rarity': rarity_enum.value,
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
    themes = get_themed_elements()
    season = get_current_season()
    time_of_day = get_time_of_day()
    
    prompt = f"Create fantasy artwork for {card_data.get('name')}. "
    
    # Add seasonal and time of day atmosphere
    prompt += f"Set in a {season} {time_of_day} atmosphere. "
    
    card_type = card_data.get('type', 'Unknown')
    if 'Creature' in card_type:
        if any(creature in card_type for creature in themes['creatures']):
            prompt += f"Show a majestic {card_type.lower()} in action. "
        else:
            prompt += f"Show a {card_type.lower()} in action. "
    elif 'Enchantment' in card_type:
        prompt += f"Depict a magical aura or mystical effect with {season} elements. "
    elif 'Artifact' in card_type:
        prompt += "Illustrate a detailed magical item or relic. "
    elif 'Land' in card_type:
        prompt += f"Illustrate a {season} landscape during {time_of_day}. "
    elif 'Planeswalker' in card_type:
        prompt += f"Show a powerful {card_type.lower()} character in a {season} setting. "
    else:
        prompt += "Depict the card's effect in a visually appealing way. "

    # Handle rarity being either string or enum
    rarity = card_data['rarity']
    if isinstance(rarity, Rarity):
        rarity = rarity.value

    # Add color and rarity-specific elements
    prompt += f"Use the {card_data['color']} color scheme with {rarity.lower()} quality. "
    
    # Add final quality instructions
    prompt += "High detail, dramatic lighting, no text or borders. "
    prompt += f"Incorporate {season} and {time_of_day} lighting effects."

    return prompt