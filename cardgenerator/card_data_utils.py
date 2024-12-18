import random
import logging
from typing import Dict, Any, List
from models import Rarity

# Logging configuration
logger = logging.getLogger(__name__)

BASE_RARITY_PROBABILITIES = {
    Rarity.COMMON: 0.714,     # ~10/14 cards in a booster
    Rarity.UNCOMMON: 0.214,   # ~3/14 cards in a booster
    Rarity.RARE: 0.062,       # ~7/8 of rare slots (7/8 * 1/14)
    Rarity.MYTHIC_RARE: 0.01  # ~1/8 of rare slots (1/8 * 1/14)
}

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
                import json
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