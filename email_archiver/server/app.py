import os
import json
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

# Import core logic (relative imports since this is a subpackage)
from email_archiver.core.utils import setup_logging
from email_archiver.core.classifier import EmailClassifier

app = FastAPI(title="EESA Web Dashboard")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'settings.yaml')
CHECKPOINT_PATH = os.path.join(BASE_DIR, 'config', 'checkpoint.json')
METADATA_PATH = os.path.join(BASE_DIR, 'email_metadata.jsonl')
UI_DIST_DIR = os.path.join(os.path.dirname(__file__), "static")

# Models
class SyncRequest(BaseModel):
    provider: str
    incremental: bool = True
    since: Optional[str] = None
    classify: bool = False
    extract: bool = False

@app.get("/api/stats")
async def get_stats():
    """Returns archive statistics."""
    stats = {
        "total_archived": 0,
        "classified": 0,
        "extracted": 0,
        "categories": {}
    }
    
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, 'r') as f:
            for line in f:
                stats["total_archived"] += 1
                try:
                    data = json.loads(line)
                    if data.get("classification"):
                        stats["classified"] += 1
                        cat = data["classification"].get("category", "unknown")
                        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
                    if data.get("extraction"):
                        stats["extracted"] += 1
                except:
                    continue
                    
    return stats

@app.get("/api/emails")
async def get_emails(limit: int = 100, skip: int = 0):
    """Returns a list of archived emails and their metadata."""
    emails = []
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, 'r') as f:
            # Reversing to get latest first if possible, or just reading
            lines = f.readlines()
            for line in reversed(lines[skip : skip + limit]):
                try:
                    emails.append(json.loads(line))
                except:
                    continue
    return emails

@app.post("/api/sync")
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """Triggers an email synchronization process in the background."""
    # This will call the main sync logic
    # For now, just a placeholder
    return {"message": f"Sync started for {request.provider}", "status": "running"}

# Serve UI Static Files
if os.path.exists(UI_DIST_DIR):
    app.mount("/", StaticFiles(directory=UI_DIST_DIR, html=True), name="static")
else:
    @app.get("/")
    async def root():
        return HTMLResponse("<h1>EESA Dashboard</h1><p>UI not built yet. Run 'npm run build' in the ui directory.</p>")

def start_server(host="127.0.0.1", port=8000):
    import uvicorn
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open(f"http://{host}:{port}")

    Timer(1.5, open_browser).start()
    uvicorn.run(app, host=host, port=port)
