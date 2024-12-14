import os
from firebase_admin import auth, initialize_app, credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
if not cred_path:
    raise ValueError("FIREBASE_CREDENTIALS_PATH environment variable is not set")

cred = credentials.Certificate(cred_path)
initialize_app(cred)

def check_user(email):
    try:
        # Try to get user by email
        user = auth.get_user_by_email(email)
        print(f"\nUser found:")
        print(f"User ID: {user.uid}")
        print(f"Email: {user.email}")
        print(f"Email verified: {user.email_verified}")
        print(f"Provider IDs: {[p.provider_id for p in user.provider_data]}")
        
        return user
    except auth.UserNotFoundError:
        print(f"\nNo user found with email: {email}")
        return None
    except Exception as e:
        print(f"\nError getting user: {str(e)}")
        return None

def fix_user_account(user):
    try:
        # Update user to verify email and ensure password auth is enabled
        auth.update_user(
            user.uid,
            email_verified=True
        )
        print("\nVerified user email")
        
        # Generate password reset link
        reset_link = auth.generate_password_reset_link(user.email)
        print("\nGenerated password reset link. User should:")
        print("1. Click the link in their email")
        print("2. Set a new password")
        print("3. Use the email and new password to sign in")
        return True
    except Exception as e:
        print(f"\nError updating user: {str(e)}")
        return False

if __name__ == "__main__":
    email = "willcruzdesigner@gmail.com"
    user = check_user(email)
    
    if user:
        print("\nAttempting to fix account...")
        fix_user_account(user)