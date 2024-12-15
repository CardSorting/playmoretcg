from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from firebase_config import verify_firebase_token, FIREBASE_CONFIG
from fastapi.templating import Jinja2Templates
import logging
import firestore_db

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize templates
templates = Jinja2Templates(directory="templates")

router = APIRouter()

async def get_current_user(request: Request) -> Optional[str]:
    """Get the current user from the Firebase ID token."""
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        return None
    
    try:
        user_id = await verify_firebase_token(auth_token)
        return user_id if user_id else None
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return None

def get_template_context(request: Request) -> dict:
    """Get common template context data."""
    return {
        "request": request,
        "firebase_config": FIREBASE_CONFIG
    }

@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Marketplace main page."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    return templates.TemplateResponse(
        "marketplace/marketplace.html",
        get_template_context(request)
    )

@router.get("/marketplace/my-listings", response_class=HTMLResponse)
async def my_listings(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """User's listing management page."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    return templates.TemplateResponse(
        "marketplace/my_listings.html",
        get_template_context(request)
    )

@router.get("/marketplace/{listing_id}", response_class=HTMLResponse)
async def view_listing(
    request: Request,
    listing_id: str,
    user_id: Optional[str] = Depends(get_current_user)
):
    """View a specific listing."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    listing = firestore_db.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    context = get_template_context(request)
    context["listing"] = listing
    return templates.TemplateResponse(
        "marketplace/listing.html",
        context
    )