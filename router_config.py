from fastapi import FastAPI
from marketplace_routes import router as marketplace_api_router
from marketplace_pages import router as marketplace_pages_router

def configure_routers(app: FastAPI):
    """Configure all routers for the application."""
    # Include marketplace routers
    app.include_router(marketplace_pages_router)
    app.include_router(marketplace_api_router)
    
    return app  # Return app for chaining if needed