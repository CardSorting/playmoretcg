# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Depends, HTTPException, Form, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import auth
import uuid

import firestore_db
from firebase_config import verify_firebase_token, FIREBASE_CONFIG
from card_generator import generate_card_image
from card_queue import card_queue, start_queue_processor, clean_old_results

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

@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup."""
    background_tasks = BackgroundTasks()
    start_queue_processor(background_tasks)
    background_tasks.add_task(clean_old_results)

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
async def explore(request: Request):
    """Public explore page."""
    context = get_template_context(request)
    # Get some random cards to display
    cards = firestore_db.get_random_cards()
    context["cards"] = cards
    return templates.TemplateResponse("explore.html", context)

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse("about.html", get_template_context(request))

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
    if not card or card.get('user_id') != user_id:
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
    user_id: Optional[str] = Depends(get_current_user)
):
    """Handle card creation."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Add to queue
        await card_queue.add_to_queue(task_id, user_id, rarity)
        
        # Return task ID for status checking
        return JSONResponse({
            "status": "queued",
            "task_id": task_id,
            "message": "Card generation started"
        })
    except Exception as e:
        logger.error(f"Error creating card: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/create/status/{task_id}")
async def check_card_status(
    task_id: str,
    user_id: Optional[str] = Depends(get_current_user)
):
    """Check the status of a card creation task."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    status = await card_queue.get_task_status(task_id)
    
    if status['status'] == 'completed':
        # Redirect to the new card
        return JSONResponse({
            "status": "completed",
            "redirect_url": f"/cards/{status['card_id']}"
        })
    elif status['status'] == 'error':
        raise HTTPException(status_code=500, detail=status['error'])
    else:
        return JSONResponse(status)

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
        # Generate unique task IDs for each card in the pack
        pack_tasks = []
        
        # Queue one Rare/Mythic Rare card
        task_id = str(uuid.uuid4())
        await card_queue.add_to_queue(task_id, user_id, "Rare")  # Will randomly become Mythic based on probability
        pack_tasks.append(task_id)
        
        # Queue three Uncommon cards
        for _ in range(3):
            task_id = str(uuid.uuid4())
            await card_queue.add_to_queue(task_id, user_id, "Uncommon")
            pack_tasks.append(task_id)
            
        # Queue six Common cards
        for _ in range(6):
            task_id = str(uuid.uuid4())
            await card_queue.add_to_queue(task_id, user_id, "Common")
            pack_tasks.append(task_id)
        
        # Return task IDs for status checking
        return JSONResponse({
            "status": "queued",
            "pack_tasks": pack_tasks,
            "message": "Pack opening started"
        })
    except Exception as e:
        logger.error(f"Error opening pack: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/packs/status")
async def check_pack_status(
    request: Request,
    task_ids: List[str],
    user_id: Optional[str] = Depends(get_current_user)
):
    """Check the status of all cards in a pack."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        statuses = []
        completed_cards = []
        all_completed = True
        
        for task_id in task_ids:
            status = await card_queue.get_task_status(task_id)
            statuses.append(status)
            
            if status['status'] == 'completed':
                # Get the card details
                card = firestore_db.get_card(status['card_id'])
                if card:
                    completed_cards.append(card)
            else:
                all_completed = False
        
        if all_completed:
            # All cards are ready, return them sorted by rarity
            sorted_cards = sorted(
                completed_cards,
                key=lambda x: ['Mythic Rare', 'Rare', 'Uncommon', 'Common'].index(x['rarity'])
            )
            return JSONResponse({
                "status": "completed",
                "cards": sorted_cards
            })
        else:
            # Some cards are still processing
            return JSONResponse({
                "status": "processing",
                "completed": len(completed_cards),
                "total": len(task_ids)
            })
            
    except Exception as e:
        logger.error(f"Error checking pack status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")