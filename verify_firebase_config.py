import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Required Firebase configuration variables
required_vars = [
    'FIREBASE_API_KEY',
    'FIREBASE_AUTH_DOMAIN',
    'FIREBASE_PROJECT_ID',
    'FIREBASE_STORAGE_BUCKET',
    'FIREBASE_MESSAGING_SENDER_ID',
    'FIREBASE_APP_ID',
    'FIREBASE_CREDENTIALS_PATH'
]

def verify_config():
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # Print the first few characters of the value (for security)
            print(f"{var}: {value[:10]}...")

    if missing_vars:
        print("\nMissing environment variables:")
        for var in missing_vars:
            print(f"- {var}")
        return False
    
    print("\nAll required Firebase configuration variables are present.")
    return True

if __name__ == "__main__":
    print("Verifying Firebase configuration...")
    verify_config()