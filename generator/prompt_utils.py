import random
from typing import Dict, Any, List
from models import Rarity

# Constants
DEFAULT_SET_NAME = 'GEN'
CARD_NUMBER_LIMIT = 999

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
    
    return prompt

def create_dalle_prompt(card_data: Dict[str, Any]) -> str:
    """Create a focused DALL-E prompt for card artwork."""
    # Extract card details
    name = card_data.get('name', '')
    card_type = card_data.get('type', '')
    color = card_data.get('color', '')
    color_str = '/'.join(color) if isinstance(color, list) else color
    
    # Start with the core subject description
    if 'Creature' in card_type:
        creature_types = card_data.get('themes', {}).get('creatures', [])
        creature_str = ' '.join(creature_types[:2]) if creature_types else card_type
        style = (
            f"Professional fantasy illustration of a {creature_str}. "
            f"Create a detailed {color_str} colored character "
            "centered in frame against a pure white background. "
            "Focus on the character's distinctive features and anatomy. "
            "The character must be the ONLY element - NO background elements, "
            "NO special effects, NO decorative elements, NO patterns. "
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
    
    return style