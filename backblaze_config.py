import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Backblaze configuration
BACKBLAZE_KEY_ID = os.getenv('BACKBLAZE_KEY_ID')
BACKBLAZE_APPLICATION_KEY = os.getenv('BACKBLAZE_APPLICATION_KEY')
BACKBLAZE_BUCKET_NAME = os.getenv('BACKBLAZE_BUCKET_NAME')
BACKBLAZE_BASE_URL = os.getenv('BACKBLAZE_BASE_URL')
BACKBLAZE_API_URL = 'https://api.backblazeb2.com'

def upload_image(image_data: bytes, filename: str) -> str:
    """
    Upload an image to Backblaze B2 and return its public URL.
    
    Args:
        image_data: The image data in bytes
        filename: The name to give the file in B2
    
    Returns:
        str: The public URL of the uploaded image
    """
    # Check if Backblaze credentials are configured
    if not all([BACKBLAZE_KEY_ID, BACKBLAZE_APPLICATION_KEY, BACKBLAZE_BUCKET_NAME, BACKBLAZE_BASE_URL]):
        print("Warning: Backblaze credentials not configured, using fallback URL")
        return f"/static/card_images/{filename}"

    try:
        # Get authorization token
        auth_response = requests.get(
            f'{BACKBLAZE_API_URL}/b2api/v2/b2_authorize_account',
            auth=(BACKBLAZE_KEY_ID, BACKBLAZE_APPLICATION_KEY)
        )
        auth_response.raise_for_status()
        auth_data = auth_response.json()
        
        # Get upload URL
        upload_url_response = requests.post(
            f'{auth_data["apiUrl"]}/b2api/v2/b2_get_upload_url',
            headers={'Authorization': auth_data['authorizationToken']},
            json={'bucketId': auth_data['allowed']['bucketId']}
        )
        upload_url_response.raise_for_status()
        upload_auth = upload_url_response.json()
        
        # Upload file
        response = requests.post(
            upload_auth['uploadUrl'],
            headers={
                'Authorization': upload_auth['authorizationToken'],
                'X-Bz-File-Name': filename,
                'Content-Type': 'image/png',
                'X-Bz-Content-Sha1': 'do_not_verify'  # For testing only
            },
            data=image_data
        )
        response.raise_for_status()
        
        # Return public URL
        return f"{BACKBLAZE_BASE_URL}/{filename}"
    except Exception as e:
        print(f"Error uploading to B2: {e}")
        # Fallback to local storage
        try:
            os.makedirs('static/card_images', exist_ok=True)
            with open(f'static/card_images/{filename}', 'wb') as f:
                f.write(image_data)
            return f"/static/card_images/{filename}"
        except Exception as e:
            print(f"Error saving to local storage: {e}")
            return "/static/default-card.png"

def delete_image(filename: str) -> bool:
    """
    Delete an image from Backblaze B2.
    
    Args:
        filename: The name of the file to delete
    
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    # Check if Backblaze credentials are configured
    if not all([BACKBLAZE_KEY_ID, BACKBLAZE_APPLICATION_KEY, BACKBLAZE_BUCKET_NAME]):
        print("Warning: Backblaze credentials not configured, using local storage")
        try:
            os.remove(f'static/card_images/{filename}')
            return True
        except Exception as e:
            print(f"Error deleting local file: {e}")
            return False

    try:
        # Get authorization
        auth_response = requests.get(
            f'{BACKBLAZE_API_URL}/b2api/v2/b2_authorize_account',
            auth=(BACKBLAZE_KEY_ID, BACKBLAZE_APPLICATION_KEY)
        )
        auth_response.raise_for_status()
        auth_data = auth_response.json()
        
        # List file versions to get file ID
        list_response = requests.post(
            f'{auth_data["apiUrl"]}/b2api/v2/b2_list_file_versions',
            headers={'Authorization': auth_data['authorizationToken']},
            json={
                'bucketId': auth_data['allowed']['bucketId'],
                'startFileName': filename,
                'maxFileCount': 1
            }
        )
        list_response.raise_for_status()
        files = list_response.json().get('files', [])
        
        if not files:
            return False
            
        file_data = files[0]
        
        # Delete file
        delete_response = requests.post(
            f'{auth_data["apiUrl"]}/b2api/v2/b2_delete_file_version',
            headers={'Authorization': auth_data['authorizationToken']},
            json={
                'fileName': filename,
                'fileId': file_data['fileId']
            }
        )
        delete_response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error deleting from B2: {e}")
        return False