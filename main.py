# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import auth
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db, sync_user, get_user_cards, create_card_for_user, get_random_cards
from firebase_config import verify_firebase_token, FIREBASE_CONFIG
from card_generator import generate_card, generate_card_image, open_pack
from models import Card, CardImage, sync_user_from_firebase

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

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[str]:
    """Get the current user from the Firebase ID token and sync with database."""
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
            # Sync with database
            sync_user(db, firebase_user)
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

def get_template_context(request: Request) -> dict:
    """Get common template context data."""
    return {
        "request": request,
        "firebase_config": FIREBASE_CONFIG
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page for all users."""
    return templates.TemplateResponse("landing.html", get_template_context(request))

@app.get("/explore", response_class=HTMLResponse)
async def explore(request: Request, db: Session = Depends(get_db)):
    """Public explore page."""
    context = get_template_context(request)
    # Get some random cards to display
    cards = get_random_cards(db)
    context["cards"] = cards
    return templates.TemplateResponse("explore.html", context)

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse("about.html", get_template_context(request))

@app.get("/collection", response_class=HTMLResponse)
async def collection(
    request: Request,
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_current_user)
):
    """User's card collection."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    try:
        cards = get_user_cards(db, user_id)
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
async def sign_in_post(request: Request, db: Session = Depends(get_db)):
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
        
        # Get Firebase user data and sync with database
        firebase_user = auth.get_user(user_id)
        sync_user(db, firebase_user)
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error in sign-in post route: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cards/{card_id}", response_class=HTMLResponse)
async def view_card(
    request: Request,
    card_id: int,
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_current_user)
):
    """View a specific card."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == user_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    context = get_template_context(request)
    context["card"] = card
    return templates.TemplateResponse("cards/card.html", context)

@app.get("/create", response_class=HTMLResponse)
async def create_card_form(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Create card form."""
    if not user_id:
        return RedirectResponse(url="/sign-in")
    
    return templates.TemplateResponse(
        "cards/create.html",
        get_template_context(request)
    )

@app.post("/create")
async def create_card_handler(
    request: Request,
    rarity: str = Form(None),
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_current_user)
):
    """Handle card creation."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Generate card data
        card_data = generate_card(rarity)
        
        # Generate and upload image
        image_url, b2_url = generate_card_image(card_data)
        filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
        
        # Create card with image
        card = create_card_for_user(db, user_id, card_data, b2_url, filename)
        
        return RedirectResponse(url=f"/cards/{card.id}", status_code=303)
    except Exception as e:
        logger.error(f"Error creating card: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_current_user)
):
    """Handle pack opening."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        pack_cards = open_pack()
        created_cards = []
        
        for card_data in pack_cards:
            # Generate and upload image
            image_url, b2_url = generate_card_image(card_data)
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            
            # Create card with image
            card = create_card_for_user(db, user_id, card_data, b2_url, filename)
            created_cards.append(card)
        
        context = get_template_context(request)
        context["cards"] = created_cards
        return templates.TemplateResponse("cards/pack_result.html", context)
    except Exception as e:
        logger.error(f"Error opening pack: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")