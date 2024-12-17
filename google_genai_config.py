import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Google Gen AI client
client = genai.Client()