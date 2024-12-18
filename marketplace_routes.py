from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Any, Optional
import logging
from models import ListingStatus
from firebase_config import verify_firebase_token
import marketplace_db
from db_ops.firestore_init import get_db
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/listings/user")

async def get_current_user(request: Request) -> Optional[int]:
    """Get the current user from the Firebase ID token."""
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        return None
    
    try:
        user_id = await verify_firebase_token(auth_token)
        return int(user_id) if user_id else None
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return None

@router.get("/active")
async def get_user_active_listings(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's active listings."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        return marketplace_db.get_user_listings(user_id, status=ListingStatus.OPEN.value, db=db)
    except Exception as e:
        logger.error(f"Error getting user's active listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get active listings")

@router.get("/sold")
async def get_user_sold_listings(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's sold listings."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        return marketplace_db.get_user_listings(user_id, status=ListingStatus.SOLD.value, db=db)
    except Exception as e:
        logger.error(f"Error getting user's sold listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sold listings")

@router.get("/purchases")
async def get_user_purchases(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's purchased items."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        return marketplace_db.get_user_purchases(user_id, db=db)
    except Exception as e:
        logger.error(f"Error getting user's purchases: {e}")
        raise HTTPException(status_code=500, detail="Failed to get purchases")

@router.get("/bids")
async def get_user_bids(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's active bids."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        return marketplace_db.get_user_active_bids(user_id, db=db)
    except Exception as e:
        logger.error(f"Error getting user's bids: {e}")
        raise HTTPException(status_code=500, detail="Failed to get bids")

@router.get("/expired")
async def get_user_expired_listings(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's expired and cancelled listings."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        expired = marketplace_db.get_user_listings(user_id, status=ListingStatus.EXPIRED.value, db=db)
        cancelled = marketplace_db.get_user_listings(user_id, status=ListingStatus.CANCELLED.value, db=db)
        return expired + cancelled
    except Exception as e:
        logger.error(f"Error getting user's expired listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get expired listings")

@router.get("/bid-history")
async def get_user_bid_history(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's complete bid history."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        return marketplace_db.get_user_bid_history(user_id, db=db)
    except Exception as e:
        logger.error(f"Error getting user's bid history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get bid history")