from pathlib import Path
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.config import RECEIPTS_DIR, BASE_DIR
from app.database import Base, engine, get_db, SessionLocal
from app.api import api_router
from app.core.currency import get_effective_base_currency

# Initialize SQLite tables safely
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Finance Hub API",
    description="Local, private, integer-precision personal finance API",
    version="2.0.0"
)

@app.on_event("startup")
def startup_base_currency_check():
    """Validates base currency consistency and enforces zero-conflict startup rules."""
    db = SessionLocal()
    try:
        get_effective_base_currency(db)
    finally:
        db.close()

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8050", "http://localhost:8050"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)

# Mount receipts for preview
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/receipts_preview", StaticFiles(directory=str(RECEIPTS_DIR)), name="receipts_preview")

# Frontend production SPA serving
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_spa(full_path: str):
        # Prevent API routes from ever serving SPA index.html
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API endpoint not found: /{full_path}"
            )
        # Serve index.html for client-side routing unless a static file matches
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", response_class=HTMLResponse)
    async def fallback_home():
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Finance Hub API</title></head>
        <body style="font-family: sans-serif; padding: 40px; background: #0E1015; color: #fff;">
            <h2>Finance Hub API (v2.0.0)</h2>
            <p>Backend is active. Frontend is building or running via Vite.</p>
            <p><a href="/docs" style="color: #38bdf8;">View Interactive API Documentation (/docs)</a></p>
        </body>
        </html>
        """
