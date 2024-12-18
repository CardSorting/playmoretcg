# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from firebase_admin import auth
import card_generator
import firestore_db
from firebase_config import verify_firebase_token, FIREBASE_CONFIG
from router_config import configure_routers

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Configure marketplace routers
configure_routers(app)

# Admin user IDs
ADMIN_USERS = {'fhn34qtflHh9rVDJsrlDnlUxn3M2'}  # Admin user

async def get_current_user(request: Request) -> Optional[str]:
    """Get the current user from the Firebase ID token and sync with Firestore."""
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        logger.debug("No auth token found")
        return None
    
    try:
        user_id = await verify_firebase_token(auth_token)
        if not user_id:
            logger.warning("Invalid or expired token")
            return None

        try:
            # Get Firebase user data
            firebase_user = auth.get_user(user_id)
            # Sync with Firestore
            user_data = {
                'email': firebase_user.email,
                'display_name': firebase_user.display_name,
                'last_login': datetime.utcnow()
            }
            firestore_db.update_user(user_id, user_data)
            logger.info(f"Authenticated user: {user_id}")
            return user_id
        except auth.UserNotFoundError:
            logger.error(f"User {user_id} not found in Firebase")
            return None
        except Exception as e:
            logger.error(f"Error syncing user data: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return None

def get_template_context(request: Request) -> Dict[str, Any]:
    """Get common template context data."""
    return {
        "request": request,
        "firebase_config": FIREBASE_CONFIG
    }

@app.get("/create", response_class=HTMLResponse)
async def create_card_form(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Admin-only card creation form."""
    if not user_id or user_id not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return templates.TemplateResponse(
        "cards/create.html",
        get_template_context(request)
    )

@app.post("/create")
async def create_card_handler(
    request: Request,
    rarity: str = Form(None),
    user_id: Optional[str] = Depends(get_current_user)
):
    """Admin-only card creation."""
    if not user_id or user_id not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Generate card data
        card_data = card_generator.generate_card(rarity)
        card_data['user_id'] = 'system'  # Created cards start unclaimed
        
        # Generate and upload image
        image_url, b2_url = card_generator.generate_card_image(card_data)
        filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
        
        # Create card in Firestore
        card = firestore_db.create_card(card_data, b2_url, filename)
        
        # Redirect to the created card
        return RedirectResponse(
            url=f"/cards/{card['id']}",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error creating card: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create card"
        )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page for all users."""
    try:
        context = get_template_context(request)
        cards = firestore_db.get_random_cards()
        context["cards"] = cards
        return templates.TemplateResponse("landing.html", context)
    except Exception as e:
        logger.error(f"Error in home route: {e}")
        context = get_template_context(request)
        context["cards"] = []  # Fallback to empty list
        context["error"] = "Unable to load cards"
        return templates.TemplateResponse("landing.html", context)

@app.get("/explore", response_class=HTMLResponse)
async def explore(request: Request):
    """Public explore page."""
    try:
        context = get_template_context(request)
        cards = firestore_db.get_random_cards()
        context["cards"] = cards
        return templates.TemplateResponse("explore.html", context)
    except Exception as e:
        logger.error(f"Error in explore route: {e}")
        context = get_template_context(request)
        context["cards"] = []  # Fallback to empty list
        context["error"] = "Unable to load cards"
        return templates.TemplateResponse("explore.html", context)

@app.get("/collection", response_class=HTMLResponse)
async def collection(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """User's card collection."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    try:
        cards = firestore_db.get_user_cards(user_id)
        context = get_template_context(request)
        context["cards"] = cards
        return templates.TemplateResponse("cards/list.html", context)
    except Exception as e:
        logger.error(f"Error in collection route: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/sign-in")
async def sign_in(request: Request):
    """Sign in page."""
    try:
        context = get_template_context(request)
        logger.info("Rendering sign-in page")
        return templates.TemplateResponse("auth/sign-in.html", context)
    except Exception as e:
        logger.error(f"Error in sign-in route: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/sign-in")
async def sign_in_post(request: Request):
    """Handle user synchronization after successful authentication."""
    try:
        # Get the token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        token = auth_header.split(' ')[1]
        
        # Verify the token and get user ID
        user_id = await verify_firebase_token(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get Firebase user data and sync with Firestore
        firebase_user = auth.get_user(user_id)
        user_data = {
            'email': firebase_user.email,
            'display_name': firebase_user.display_name,
            'last_login': datetime.utcnow()
        }
        firestore_db.create_user(user_id, user_data)
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error in sign-in post route: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cards/{card_id}", response_class=HTMLResponse)
async def view_card(
    request: Request,
    card_id: str,
    user_id: Optional[str] = Depends(get_current_user)
):
    """View a specific card."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    card = firestore_db.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
        
    # Allow admins to view any card, but regular users can only view their own
    if user_id not in ADMIN_USERS and card.get('user_id') != user_id:
        raise HTTPException(status_code=404, detail="Card not found")
    
    context = get_template_context(request)
    context["card"] = card
    return templates.TemplateResponse("cards/card.html", context)

@app.get("/packs", response_class=HTMLResponse)
async def open_pack_form(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Pack opening form."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    return templates.TemplateResponse(
        "cards/pack.html",
        get_template_context(request)
    )

@app.post("/packs")
async def open_pack_action(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Handle pack opening."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Open pack and get claimed cards
        cards = firestore_db.open_pack(user_id)
        
        # Build the URL with card IDs
        card_ids = [f"card_id={card['id']}" for card in cards]
        url = f"/packs/result?{'&'.join(card_ids)}"
        return RedirectResponse(url=url, status_code=303)
    except ValueError as e:
        # Handle specific errors like no available cards
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error opening pack: {e}")
        raise HTTPException(status_code=500, detail="Failed to open pack")

@app.get("/packs/result", response_class=HTMLResponse)
async def pack_result(
    request: Request,
    card_ids: List[str],
    user_id: Optional[str] = Depends(get_current_user)
):
    """Display pack opening results."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    try:
        cards = []
        for card_id in card_ids:
            card = firestore_db.get_card(card_id)
            if card and card.get('user_id') == user_id:
                cards.append(card)
        
        if not cards:
            raise HTTPException(status_code=404, detail="No cards found")
        
        context = get_template_context(request)
        context["cards"] = sorted(
            cards,
            key=lambda x: ['Mythic Rare', 'Rare', 'Uncommon', 'Common'].index(x['rarity'])
        )
        return templates.TemplateResponse("cards/pack_result.html", context)
    except Exception as e:
        logger.error(f"Error displaying pack result: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")