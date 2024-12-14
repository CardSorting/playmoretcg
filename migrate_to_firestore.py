from database import SessionLocal
import firestore_db
from models import Base, User, Card, CardImage
import sys

def migrate():
    """Migrate all data from SQLite to Firestore."""
    try:
        # Create SQLite session
        db = SessionLocal()
        
        # Perform migration
        print("Starting migration from SQLite to Firestore...")
        print("Migrating users and their cards...")
        
        # Use the migration function from firestore_db
        firestore_db.migrate_from_sqlite(db)
        
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)