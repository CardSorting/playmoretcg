import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime

def test_firestore_connection():
    """Test Firestore connection by creating and reading a test document."""
    try:
        # Initialize Firebase Admin SDK
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'cred/playmoretcg-774b1-firebase-adminsdk-dnfs3-c0010bde40.json')
        cred = credentials.Certificate(cred_path)
        
        try:
            firebase_admin.initialize_app(cred)
        except ValueError:
            # App already initialized
            pass
        
        # Get Firestore client
        db = firestore.client()
        
        # Create a test document
        test_data = {
            'message': 'Test document',
            'timestamp': datetime.utcnow(),
            'test': True
        }
        
        print("Creating test document...")
        doc_ref = db.collection('test').document('test_doc')
        doc_ref.set(test_data)
        
        # Read the document back
        print("Reading test document...")
        doc = doc_ref.get()
        if doc.exists:
            print("Test document exists:", doc.to_dict())
            
            # Clean up
            print("Cleaning up test document...")
            doc_ref.delete()
            print("Test document deleted")
            
            print("\nFirestore connection test successful!")
            return True
        else:
            print("Error: Test document not found")
            return False
            
    except Exception as e:
        print(f"Error testing Firestore connection: {e}")
        return False

if __name__ == "__main__":
    test_firestore_connection()