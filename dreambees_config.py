import os
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

def generate_content(prompt: str) -> str:
    """Generate content using DreamBees LLM API."""
    url = "https://api.dreambeesart.com/api/llm/generate/"
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    headers = {
        'Content-Type': 'application/json'
    }
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()['text']