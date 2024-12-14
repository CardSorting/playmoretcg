import os
from typing import Optional, Dict, Any
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firebase configuration
FIREBASE_CONFIG = {
    "apiKey": os.getenv('FIREBASE_API_KEY'),
    "authDomain": os.getenv('FIREBASE_AUTH_DOMAIN'),
    "projectId": os.getenv('FIREBASE_PROJECT_ID'),
    "storageBucket": os.getenv('FIREBASE_STORAGE_BUCKET'),
    "messagingSenderId": os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    "appId": os.getenv('FIREBASE_APP_ID'),
    "measurementId": os.getenv('FIREBASE_MEASUREMENT_ID')
}

# Initialize Firebase Admin SDK
cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
if not cred_path:
    raise ValueError("FIREBASE_CREDENTIALS_PATH environment variable is not set")

cred = credentials.Certificate(cred_path)

# Initialize the app
try:
    firebase_app = firebase_admin.initialize_app(cred)
except ValueError:
    # App already initialized
    firebase_app = firebase_admin.get_app()

async def verify_firebase_token(token: Optional[str] = None) -> Optional[str]:
    """
    Verify Firebase ID token and return user ID.
    
    Args:
        token: Firebase ID token
        
    Returns:
        str: User ID if token is valid, None otherwise
    """
    if not token:
        return None
        
    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None

def get_firebase_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get Firebase user data by user ID.
    
    Args:
        user_id: Firebase user ID
        
    Returns:
        dict: User data if found, None otherwise
    """
    try:
        user = auth.get_user(user_id)
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'photo_url': user.photo_url,
            'email_verified': user.email_verified
        }
    except auth.UserNotFoundError:
        return None
    except Exception as e:
        print(f"Error getting Firebase user: {e}")
        return None

def create_firebase_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Create a new Firebase user.
    
    Args:
        email: User email
        password: User password
        
    Returns:
        dict: Created user data if successful, None otherwise
    """
    try:
        user = auth.create_user(
            email=email,
            password=password
        )
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name
        }
    except Exception as e:
        print(f"Error creating Firebase user: {e}")
        return None

def update_firebase_user(user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update Firebase user data.
    
    Args:
        user_id: Firebase user ID
        **kwargs: User properties to update
        
    Returns:
        dict: Updated user data if successful, None otherwise
    """
    try:
        user = auth.update_user(
            user_id,
            **kwargs
        )
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'photo_url': user.photo_url,
            'email_verified': user.email_verified
        }
    except Exception as e:
        print(f"Error updating Firebase user: {e}")
        return None

def delete_firebase_user(user_id: str) -> bool:
    """
    Delete a Firebase user.
    
    Args:
        user_id: Firebase user ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        auth.delete_user(user_id)
        return True
    except Exception as e:
        print(f"Error deleting Firebase user: {e}")
        return False