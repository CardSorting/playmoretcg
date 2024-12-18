import logging
import requests
from typing import Dict, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_random_exponential
from openai_config import openai_client
from backblaze_config import upload_image

# Logging configuration
logger = logging.getLogger(__name__)

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