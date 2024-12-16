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
    Rarity.COMMON: 0.714,     # ~10/14 cards in a booster
    Rarity.UNCOMMON: 0.214,   # ~3/14 cards in a booster
    Rarity.RARE: 0.062,       # ~7/8 of rare slots (7/8 * 1/14)
    Rarity.MYTHIC_RARE: 0.01  # ~1/8 of rare slots (1/8 * 1/14)
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

# Common MTG themes by color
COLOR_THEMES = {
    'White': {
        'creatures': ['Angel', 'Knight', 'Soldier', 'Cleric', 'Bird', 'Cat', 'Unicorn', 'Griffin', 'Pegasus', 'Human'],
        'keywords': ['Vigilance', 'Protection', 'Lifelink', 'First Strike', 'Flying', 'Exile', 'Shield', 'Unity', 'Divine', 'Order']
    },
    'Blue': {
        'creatures': ['Wizard', 'Merfolk', 'Sphinx', 'Drake', 'Illusion', 'Serpent', 'Leviathan', 'Djinn', 'Shapeshifter', 'Elemental'],
        'keywords': ['Flying', 'Scry', 'Counter', 'Bounce', 'Draw', 'Control', 'Knowledge', 'Mind', 'Illusion', 'Manipulation']
    },
    'Black': {
        'creatures': ['Zombie', 'Vampire', 'Demon', 'Horror', 'Skeleton', 'Wraith', 'Shade', 'Specter', 'Rat', 'Nightmare'],
        'keywords': ['Deathtouch', 'Lifelink', 'Sacrifice', 'Destroy', 'Drain', 'Corrupt', 'Death', 'Decay', 'Dark', 'Torment']
    },
    'Red': {
        'creatures': ['Dragon', 'Goblin', 'Warrior', 'Phoenix', 'Elemental', 'Ogre', 'Devil', 'Giant', 'Shaman', 'Berserker'],
        'keywords': ['Haste', 'First Strike', 'Direct Damage', 'Trample', 'Fury', 'Rage', 'Burn', 'Chaos', 'Lightning', 'Fire']
    },
    'Green': {
        'creatures': ['Beast', 'Elf', 'Druid', 'Wurm', 'Hydra', 'Treefolk', 'Spider', 'Wolf', 'Bear', 'Dinosaur'],
        'keywords': ['Trample', 'Reach', 'Fight', 'Growth', 'Ramp', 'Natural', 'Wild', 'Primal', 'Forest', 'Strength']
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

# Color weights by rarity
COLOR_WEIGHTS = {
    Rarity.COMMON: {'mono': 1.0},
    Rarity.UNCOMMON: {'mono': 0.8, 'guild': 0.2},
    Rarity.RARE: {'mono': 0.6, 'guild': 0.3, 'shard': 0.1},
    Rarity.MYTHIC_RARE: {'mono': 0.4, 'guild': 0.4, 'shard': 0.2}
}

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

def get_themed_elements(colors: List[str]) -> Dict[str, Any]:
    """Get themed elements based on card colors."""
    creatures = []
    keywords = []
    
    # Gather themes from each color
    for color in colors:
        color_creatures = COLOR_THEMES[color]['creatures']
        color_keywords = COLOR_THEMES[color]['keywords']
        
        # Add 2-3 random creatures and keywords from each color
        creatures.extend(random.sample(color_creatures, min(random.randint(2, 3), len(color_creatures))))
        keywords.extend(random.sample(color_keywords, min(random.randint(2, 3), len(color_keywords))))
    
    # Remove duplicates while preserving order
    creatures = list(dict.fromkeys(creatures))
    keywords = list(dict.fromkeys(keywords))
    
    return {
        'creatures': creatures,
        'keywords': keywords,
        'colors': colors
    }

def generate_card_prompt(rarity: str = None) -> str:
    """Generate the GPT prompt for creating the card."""
    if not rarity:
        rarity_options = ', '.join([r.value for r in Rarity])
        rarity_prompt = f"Choose from: {rarity_options}"
    else:
        rarity_prompt = rarity
        rarity_enum = Rarity[rarity.upper().replace(' ', '_')]
    
    # Get card type and color combination if rarity is specified
    card_type = get_card_type(rarity_enum) if rarity else "any appropriate type"
    colors = get_color_combination(rarity_enum) if rarity else [random.choice(MONO_COLORS)]
    color_str = '/'.join(colors)
    
    # Get themed elements based on colors
    themes = get_themed_elements(colors)
    
    # Simple mana cost guidance
    mana_cost_guidance = ""
    if rarity:
        color_symbols = ''.join(f"{{{c[0]}}}" for c in colors)  # First letter of each color
        mana_cost_guidance = f"Use {' and '.join(colors)} mana symbols with optional generic mana. "
        mana_cost_guidance += f"Example: {'{2}' + color_symbols} for a 4-cost card."
    
    # Build the prompt with emphasis on concise, focused design
    prompt = (
        f"Design a focused Magic: The Gathering card with these specifications:\n"
        f"- Name: Brief, thematic name (max 40 chars) using elements from {', '.join(themes['creatures'][:2])}.\n"
        f"- ManaCost: {mana_cost_guidance if mana_cost_guidance else 'Balanced mana cost with curly braces {X}.'}\n"
        f"- Type: {card_type}\n"
        f"- Color: {color_str}\n"
        "- Abilities: Create 1-3 concise, synergistic abilities that:\n"
        f"  * Incorporate these keywords: {', '.join(random.sample(themes['keywords'], min(2, len(themes['keywords']))))}\n"
        "  * Focus on clear, direct effects\n"
        "  * Each ability should be under 150 characters\n"
        "  * Prefer established keyword mechanics when possible\n"
        "- PowerToughness: For creatures, use balanced stats matching the mana cost.\n"
        f"- FlavorText: One impactful sentence (max 120 chars) capturing the card's essence.\n"
        f"- Rarity: {rarity_prompt}\n"
        "Return a JSON object with these fields. Keep text concise and focused."
    )
    
    # Log the final prompt
    logger.info(f"Generated DALL-E prompt: {prompt}")
    return prompt

def safe_get_dict(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get a value from a dictionary, providing a default if the key is missing."""
    return data.get(key, default)

def standardize_card_data(card_data: Dict[str, Any]) -> None:
    """Standardizes card data fields and ensures all required fields are present with length validation."""
    # Character limits for different fields
    LIMITS = {
        'name': 40,
        'abilities': 150,  # per ability
        'flavorText': 120,
        'type': 50
    }
    
    mapping = {
        'Name': 'name',
        'ManaCost': 'manaCost',
        'Type': 'type',
        'Color': 'color',
        'Abilities': 'abilities',
        'FlavorText': 'flavorText',
        'Rarity': 'rarity',
        'PowerToughness': 'powerToughness',
        'Power': 'power',
        'Toughness': 'toughness'
    }

    # Transfer uppercase values to lowercase fields if present
    for old_key, new_key in mapping.items():
        if old_key in card_data:
            card_data[new_key] = card_data.pop(old_key)
    
    # Format abilities with length validation
    if 'abilities' in card_data:
        abilities = card_data['abilities']
        
        # Convert string to list if needed
        if isinstance(abilities, str):
            try:
                # Try to parse as JSON if it's a string representation of JSON
                abilities = json.loads(abilities)
            except json.JSONDecodeError:
                # If not JSON, split by newlines and filter empty lines
                abilities = [line.strip() for line in abilities.splitlines() if line.strip()]
        
        # Ensure abilities is a list
        if not isinstance(abilities, list):
            abilities = [str(abilities)]
        
        # Format each ability with length limits
        formatted_abilities = []
        for ability in abilities:
            if isinstance(ability, dict):
                desc = ability.get('Description', '')
                if ability.get('Type') == 'Activated' and ability.get('Cost'):
                    desc = f"{ability['Cost']}: {desc}"
                # Truncate description if too long
                if len(desc) > LIMITS['abilities']:
                    desc = desc[:LIMITS['abilities']-3] + '...'
                formatted_abilities.append(desc)
            else:
                ability_text = str(ability)
                # Truncate ability text if too long
                if len(ability_text) > LIMITS['abilities']:
                    ability_text = ability_text[:LIMITS['abilities']-3] + '...'
                formatted_abilities.append(ability_text)
        
        # Limit total number of abilities
        if len(formatted_abilities) > 4:
            formatted_abilities = formatted_abilities[:4]
            logger.warning(f"Card {card_data.get('name', 'Unknown')} had too many abilities, truncated to 4")
        
        # Join abilities with line breaks
        card_data['abilities'] = '<br>'.join(formatted_abilities)
    
    # Handle power/toughness
    if 'type' in card_data and 'Creature' in card_data['type']:
        power = card_data.get('power', card_data.get('Power', '0'))
        toughness = card_data.get('toughness', card_data.get('Toughness', '0'))
        card_data['powerToughness'] = f"{power}/{toughness}"
    else:
        card_data['powerToughness'] = ''
    
    # Validate required fields
    required_fields = ['name', 'manaCost', 'type', 'color', 'abilities', 'flavorText', 'rarity']
    for field in required_fields:
        if field not in card_data or not card_data[field]:
            card_data[field] = get_default_value_for_field(field)

    # Convert rarity string to enum if it's a string
    if isinstance(card_data.get('rarity'), str):
        try:
            card_data['rarity'] = Rarity[card_data['rarity'].upper().replace(' ', '_')]
        except KeyError:
            card_data['rarity'] = Rarity.COMMON

    # Convert rarity enum to string value for Firestore
    if isinstance(card_data.get('rarity'), Rarity):
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

def get_next_set_name_and_number() -> Tuple[str, int, int]:
    """Get the next set name, set number, and card number."""
    set_number = random.randint(1, 10)
    return DEFAULT_SET_NAME, set_number, random.randint(1, CARD_NUMBER_LIMIT)

def validate_card_data(card_data: Dict[str, Any]) -> bool:
    """Validate the generated card data meets requirements and length limits."""
    required_fields = ['name', 'manaCost', 'type', 'color', 'abilities', 'flavorText', 'rarity']
    
    # Length limits for validation
    LIMITS = {
        'name': 40,
        'type': 50,
        'flavorText': 120,
        'manaCost': 20
    }
    
    # Check all required fields are present, non-empty, and within length limits
    for field in required_fields:
        if not card_data.get(field):
            logger.error(f"Missing or empty required field: {field}")
            return False
        
        # Check length limits for text fields
        if field in LIMITS and len(str(card_data[field])) > LIMITS[field]:
            logger.error(f"Field {field} exceeds length limit of {LIMITS[field]} characters")
            return False
    
    # Validate mana cost format (should contain curly braces)
    if not ('{' in card_data['manaCost'] and '}' in card_data['manaCost']):
        logger.error("Invalid mana cost format")
        return False
    
    # Validate card type
    valid_types = ['Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Planeswalker']
    if not any(type_word in card_data['type'] for type_word in valid_types):
        logger.error("Invalid card type")
        return False
    
    # Validate color
    if not isinstance(card_data.get('color'), (str, list)):
        logger.error("Invalid color format")
        return False
    
    # Validate abilities format and count
    if isinstance(card_data['abilities'], str):
        abilities = card_data['abilities'].split('<br>')
        if len(abilities) > 4:
            logger.error("Too many abilities (maximum 4 allowed)")
            return False
        for ability in abilities:
            if len(ability) > 150:  # Max length per ability
                logger.error("Ability text too long (maximum 150 characters per ability)")
                return False
    
    return True

def get_rarity(set_number: int, card_number: int) -> Rarity:
    """Determine card rarity based on set and card number."""
    # Base probabilities
    probabilities = BASE_RARITY_PROBABILITIES.copy()

    # Adjust probabilities based on set number
    if set_number % 3 == 0:  # Sets divisible by 3 have slightly higher chance of rare/mythic
        probabilities[Rarity.RARE] += 0.01
        probabilities[Rarity.MYTHIC_RARE] += 0.005
        probabilities[Rarity.COMMON] -= 0.01
        probabilities[Rarity.UNCOMMON] -= 0.005
    elif set_number % 2 == 0:  # Sets divisible by 2 have slightly higher chance of uncommon
        probabilities[Rarity.UNCOMMON] += 0.01
        probabilities[Rarity.COMMON] -= 0.01

    # Adjust probabilities based on card number
    if card_number % 100 == 0:  # Every 100th card is more likely to be mythic
        probabilities[Rarity.MYTHIC_RARE] += 0.02
        probabilities[Rarity.RARE] += 0.01
        probabilities[Rarity.COMMON] -= 0.02
        probabilities[Rarity.UNCOMMON] -= 0.01
    elif card_number % 10 == 0:  # Every 10th card is more likely to be rare
        probabilities[Rarity.RARE] += 0.02
        probabilities[Rarity.COMMON] -= 0.02

    # Normalize probabilities
    total = sum(probabilities.values())
    normalized_probabilities = {k: v / total for k, v in probabilities.items()}

    # Choose rarity based on normalized probabilities
    rarity = random.choices(
        list(normalized_probabilities.keys()),
        weights=list(normalized_probabilities.values())
    )[0]
    return rarity

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

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(5))
def generate_card_image(card_data: Dict[str, Any]) -> Tuple[str, str]:
    """Generate artwork for the card using OpenAI's image generation API."""
    logger.info(f"\n=== Generating image for card: {card_data.get('name')} ===")
    
    # Get card details
    card_type = card_data.get('type', 'Unknown')
    color_str = card_data.get('color', '')
    if isinstance(color_str, list):
        color_str = '/'.join(color_str)
    
    # Create a focused prompt for the image
    prompt = (
        f"Professional fantasy character art of a {card_type.lower()} for Magic card. "
        f"Create ONLY the main character in {color_str} colors, centered in frame. "
        "Use a completely plain white background. "
        "NO background elements, NO patterns, NO decorative effects - ONLY the character. "
        "Style: Detailed digital art like a 3D model render. "
        "Think character turnaround reference art."
    )
    max_attempts = 3

    for attempt in range(max_attempts):
        logger.info(f"\nAttempt {attempt + 1} of {max_attempts}")
        try:
            # Log DALL-E request
            logger.info("\nSending request to DALL-E API:")
            logger.info(f"Model: dall-e-3")
            logger.info(f"Size: 1024x1024")
            logger.info(f"Quality: hd")  # Use HD quality for better detail
            logger.info(f"Style: vivid")  # Use vivid for stronger artistic direction
            logger.info(f"Prompt: {prompt}")
            
            # Generate image with DALL-E
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="hd",  # Higher quality
                n=1,
                style="vivid"  # Better for fantasy art
            )
            
            # Log DALL-E response
            image_url = response.data[0].url
            logger.info("\nReceived response from DALL-E API:")
            logger.info(f"Image URL: {image_url}")
            if hasattr(response.data[0], 'revised_prompt'):
                logger.info(f"Revised prompt: {response.data[0].revised_prompt}")
            
            # Download image from OpenAI with timeout and retries
            download_attempts = 3
            for dl_attempt in range(download_attempts):
                try:
                    response = requests.get(image_url, timeout=30)
                    if response.status_code == 200:
                        break
                    logger.warning(f"Failed to download image (attempt {dl_attempt + 1}): Status {response.status_code}")
                    if dl_attempt == download_attempts - 1:
                        raise ValueError(f"Failed to download image after {download_attempts} attempts")
                except requests.RequestException as e:
                    if dl_attempt == download_attempts - 1:
                        raise
                    logger.warning(f"Download attempt {dl_attempt + 1} failed: {e}")
            
            # Prepare image data for upload
            image_data = response.content
            if not image_data:
                raise ValueError("Downloaded image data is empty")
                
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            
            # Upload to Backblaze with validation
            try:
                b2_url = upload_image(image_data, filename)
                if not b2_url:
                    raise ValueError("Failed to get valid URL from Backblaze upload")
                return image_url, b2_url
            except Exception as e:
                logger.error(f"Backblaze upload error: {e}")
                if attempt < max_attempts - 1:
                    continue
                raise
            
        except Exception as e:
            logger.error(f"Error generating card image (attempt {attempt + 1}): {e}")
            if attempt < max_attempts - 1:
                continue
            raise ValueError(f"Failed to generate and store card image after {max_attempts} attempts: {str(e)}")

def create_dalle_prompt(card_data: Dict[str, Any]) -> str:
    """Create a focused DALL-E prompt for card artwork."""
    # Extract card details
    name = card_data.get('name', '')
    card_type = card_data.get('type', '').replace(' - ', ' ').split(' ')  # Split type into parts
    color = card_data.get('color', '')
    color_str = '/'.join(color) if isinstance(color, list) else color
    
    # Start with the core subject description
    if 'Creature' in card_type:
        # Extract creature types and use them in the prompt
        creature_types = ' '.join(card_type[2:]) if len(card_type) > 2 else 'creature'
        style = (
            f"Professional fantasy illustration of a {creature_types}. "
            f"Create a detailed {color_str} colored {creature_types} character "
            "centered in frame against a pure white background. "
            "Focus on the character's distinctive features and anatomy. "
            "The character must be the ONLY element - NO background elements, "
            "NO special effects, NO decorative elements, NO patterns. "
            "Style: High-detail digital artlike a character concept art piece. "
            "Think professional fantasy character art on a pure white studio backdrop."
        )
    else:
        # For non-creature cards, be specific about what we want based on card type
        if 'Enchantment' in card_type:
            style = (
                f"Professional illustration of a single {color_str} magical crystal or orb "
                "floating in empty space. Crystal/orb must be the ONLY element, centered "
                "against a pure white background. NO effects, NO patterns, NO decorative elements. "
                "Think high-end jewelry photography on white backdrop."
            )
        elif 'Artifact' in card_type:
            style = (
                f"Professional illustration of a single {color_str} magical artifact "
                "floating in empty space. Artifact must be the ONLY element, centered "
                "against a pure white background. NO effects, NO patterns, NO decorative elements. "
                "Think product photography of a precious object on white backdrop."
            )
        elif 'Instant' in card_type or 'Sorcery' in card_type:
            style = (
                f"Professional illustration of a single {color_str} magical rune or sigil "
                "floating in empty space. Rune/sigil must be the ONLY element, centered "
                "against a pure white background. NO effects, NO patterns, NO decorative elements. "
                "Think minimalist magical symbol on white backdrop."
            )
        else:
            style = (
                f"Professional illustration of a single {color_str} magical object "
                "floating in empty space. Object must be the ONLY element, centered "
                "against a pure white background. NO effects, NO patterns, NO decorative elements. "
                "Think product photography on white backdrop."
            )
    
    # Log the prompt
    logger.info(f"Generated DALL-E prompt for {name}:")
    logger.info(style)
    
    return style

def generate_card_image(card_data: Dict[str, Any]) -> Tuple[str, str]:
    """Generate artwork for the card using OpenAI's image generation API."""
    logger.info(f"\n=== Generating image for card: {card_data.get('name')} ===")
    prompt = create_dalle_prompt(card_data)
    max_attempts = 3
    last_error = None

    for attempt in range(max_attempts):
        try:
            # Log DALL-E request
            logger.info("\nSending request to DALL-E API:")
            logger.info(f"Model: dall-e-3")
            logger.info(f"Size: 1024x1024")
            logger.info(f"Quality: hd")
            logger.info(f"Style: vivid")
            logger.info(f"Prompt: {prompt}")
            
            # Generate image with DALL-E
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="hd",
                n=1,
                style="vivid"
            )
            
            # Get the image URL
            dalle_url = response.data[0].url
            logger.info("\nReceived response from DALL-E API:")
            logger.info(f"Image URL: {dalle_url}")
            
            if not dalle_url:
                raise ValueError("Failed to get valid URL from DALL-E")
            
            # Download and upload to Backblaze
            response = requests.get(dalle_url, timeout=30)
            if response.status_code != 200:
                raise ValueError(f"Failed to download image: Status {response.status_code}")
            
            image_data = response.content
            if not image_data:
                raise ValueError("Downloaded image data is empty")
            
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            b2_url = upload_image(image_data, filename)
            
            if not b2_url:
                raise ValueError("Failed to get valid URL from Backblaze upload")
            
            return dalle_url, b2_url
            
        except Exception as e:
            logger.error(f"Error generating card image (attempt {attempt + 1}): {e}")
            last_error = e
            logger.warning(f"Attempt {attempt + 1} failed, {'retrying' if attempt < max_attempts - 1 else 'giving up'}")
            continue
    
    # If we've exhausted all attempts, raise the last error
    if last_error:
        logger.error(f"All {max_attempts} attempts failed")
        raise ValueError(f"Failed to generate and store card image: {str(last_error)}")
    
    # This should never be reached as we either return in the try block or raise in the error handling
    raise ValueError("Unexpected error in image generation")
    
    return prompt