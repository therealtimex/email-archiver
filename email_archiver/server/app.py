import os
import json
import logging
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime
import yaml

# Import core logic
from email_archiver.core.utils import setup_logging
from email_archiver.core.classifier import EmailClassifier
from email_archiver.core.db_handler import DBHandler
from email_archiver.core.paths import (
    get_config_path, 
    get_auth_dir, 
    get_data_dir, 
    resolve_path
)

app = FastAPI(title="EESA Web Dashboard")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

# Paths
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = get_config_path()
TEMPLATES_DIR = os.path.join(SERVER_DIR, "templates")
STATIC_DIR = os.path.join(SERVER_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Initialize DB
db = DBHandler()

# Global state for sync progress
sync_status = {
    "is_running": False,
    "is_cancelled": False,
    "last_run": None,
    "current_task": None,
    "progress": 0,
    "logs": []
}

class UILogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        sync_status["logs"].append(log_entry)
        # Keep only last 100 logs
        if len(sync_status["logs"]) > 100:
            sync_status["logs"].pop(0)

ui_log_handler = UILogHandler()
ui_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

class SyncRequest(BaseModel):
    provider: str
    incremental: bool = True
    classify: bool = False
    extract: bool = False
    rename: bool = False
    embed: bool = False
    since: Optional[str] = None
    after_id: Optional[str] = None
    specific_id: Optional[str] = None
    query: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    local_only: bool = False

class AuthRequest(BaseModel):
    provider: str
    code: Optional[str] = None
    flow: Optional[Dict[str, Any]] = None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/version")
async def get_version():
    """Returns the current project version."""
    from email_archiver import __version__
    return {"version": __version__}

@app.get("/api/settings")
async def get_settings():
    """Reads the current settings from settings.yaml."""
    from email_archiver.main import load_config
    return load_config(CONFIG_PATH)

@app.post("/api/settings")
async def update_settings(new_settings: Dict[str, Any]):
    """Updates the settings.yaml file."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(new_settings, f, default_flow_style=False)
        return {"message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving config: {e}")

@app.get("/api/auth/status")
async def get_auth_status():
    """Checks if providers are authenticated."""
    auth_dir = get_auth_dir()
    gmail_token = auth_dir / 'gmail_token.json'
    m365_token = auth_dir / 'm365_token.json'
    
    return {
        "gmail": os.path.exists(gmail_token),
        "m365": os.path.exists(m365_token)
    }

@app.post("/api/auth/init")
async def init_auth(request: AuthRequest):
    """Initiates the auth flow for a provider."""
    from email_archiver.main import load_config
    config = load_config(CONFIG_PATH)
    
    if request.provider == 'gmail':
        from email_archiver.core.gmail_handler import GmailHandler
        try:
            handler = GmailHandler(config)
            url = handler.get_auth_url()
            return {"url": url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    elif request.provider == 'm365':
        from email_archiver.core.graph_handler import GraphHandler
        try:
            handler = GraphHandler(config)
            flow = handler.initiate_device_flow()
            return {"flow": flow}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    raise HTTPException(status_code=400, detail="Invalid provider")

@app.post("/api/auth/complete")
async def complete_auth(request: AuthRequest):
    """Completes the auth flow."""
    from email_archiver.main import load_config
    config = load_config(CONFIG_PATH)
    
    if request.provider == 'gmail':
        if not request.code:
            raise HTTPException(status_code=400, detail="Code is required for Gmail")
        from email_archiver.core.gmail_handler import GmailHandler
        try:
            handler = GmailHandler(config)
            handler.submit_code(request.code)
            return {"message": "Gmail authenticated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    elif request.provider == 'm365':
        if not request.flow:
            raise HTTPException(status_code=400, detail="Flow data is required for M365")
        from email_archiver.core.graph_handler import GraphHandler
        try:
            handler = GraphHandler(config)
            success = await asyncio.to_thread(handler.complete_device_flow, request.flow)
            if success:
                return {"message": "M365 authenticated successfully"}
            else:
                raise HTTPException(status_code=400, detail="M365 authentication failed or timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    raise HTTPException(status_code=400, detail="Invalid provider")

@app.post("/api/secrets")
async def save_secrets(provider: str, data: Dict[str, Any]):
    """Saves provider secrets (like credentials.json) to the auth/ directory."""
    try:
        auth_dir = get_auth_dir()
        os.makedirs(auth_dir, exist_ok=True)
        if provider == 'gmail':
            path = auth_dir / 'credentials.json'
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return {"message": "Gmail credentials saved"}
        elif provider == 'm365':
            path = auth_dir / 'config.json'
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return {"message": "M365 config saved"}
        raise HTTPException(status_code=400, detail="Invalid provider for secrets")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    return db.get_stats()

@app.get("/api/ai-stats")
async def get_ai_stats():
    """Returns AI processing statistics (success/failure rates)."""
    return db.get_ai_stats()

@app.get("/api/llm-status")
async def get_llm_status():
    """Returns current LLM health status."""
    # Check if sync is running and get status from the running classifier
    if sync_status.get("is_running"):
        # During sync, we can't easily access the classifier instance
        # So we return the sync status
        return {
            "status": "checking",
            "message": "Sync in progress, status will update"
        }

    # When not syncing, do a quick health check
    try:
        from email_archiver.main import load_config
        config = load_config(CONFIG_PATH)
        classifier = EmailClassifier(config)

        if not classifier.enabled:
            return {
                "status": "disabled",
                "message": "AI classification is not enabled"
            }

        # Quick health check
        is_healthy = classifier.check_health()

        if is_healthy:
            return {
                "status": "online",
                "message": f"LLM is reachable ({classifier.base_url or 'OpenAI'})",
                "endpoint": classifier.base_url or "OpenAI",
                "model": classifier.model
            }
        else:
            error_reason = classifier.error_handler.circuit_breaker.get('open_reason', 'Unknown error')
            return {
                "status": "offline",
                "message": f"LLM is unreachable: {error_reason}",
                "endpoint": classifier.base_url or "OpenAI"
            }
    except Exception as e:
        logging.error(f"Error checking LLM status: {e}")
        return {
            "status": "error",
            "message": f"Error checking status: {str(e)}"
        }

@app.get("/api/emails")
async def get_emails(limit: int = 50, skip: int = 0, search: Optional[str] = None):
    return db.get_emails(limit=limit, offset=skip, search_query=search)

@app.get("/api/emails/{message_id}/download")
async def download_email(message_id: str):
    """Downloads the raw .eml file for an email."""
    # Since message_id might be URL encoded by the client, FastAPI decodes it automatically.
    # However, if it contains slashes, it might be tricky. M365 IDs are usually safe base64url.
    
    email = db.get_email(message_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    file_path = email.get("file_path")
    if not file_path:
         raise HTTPException(status_code=404, detail="File path not recorded for this email")

    # Resolve path (in case it's relative or just to be safe)
    try:
        abs_path = resolve_path(file_path)
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error resolving file path: {e}")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Email file not found on disk")
        
    # Sanitize filename for download
    filename = os.path.basename(abs_path)
    
    return FileResponse(
        path=abs_path, 
        filename=filename, 
        media_type='message/rfc822'
    )

async def run_sync_task(provider: str, incremental: bool, classify: bool, extract: bool, rename: bool = False, embed: bool = False, since: Optional[str] = None, after_id: Optional[str] = None, specific_id: Optional[str] = None, query: Optional[str] = None, llm_base_url: Optional[str] = None, llm_api_key: Optional[str] = None, llm_model: Optional[str] = None, local_only: bool = False):
    global sync_status
    sync_status["is_running"] = True
    sync_status["is_cancelled"] = False # Reset cancellation state
    sync_status["progress"] = 0
    sync_status["logs"] = [] # Clear old logs
    
    # Attach our log handler to the root logger while sync is running
    root_logger = logging.getLogger()
    root_logger.addHandler(ui_log_handler)
    
    try:
        logging.info(f"Initiating sync for provider: {provider}")
        from email_archiver.main import run_archiver_logic
        
        await asyncio.to_thread(run_archiver_logic, provider, incremental, classify, extract, since, after_id, specific_id, query, rename, embed, llm_api_key, llm_model, llm_base_url, local_only)
        
        logging.info("Synchronization completed successfully.")
        sync_status["last_run"] = datetime.now().isoformat()
    except Exception as e:
        logging.error(f"Synchronization failed: {e}")
    finally:
        sync_status["is_running"] = False
        sync_status["progress"] = 100
        root_logger.removeHandler(ui_log_handler)

@app.post("/api/stop")
async def stop_server(background_tasks: BackgroundTasks):
    """Gracefully stops the server."""
    logging.info("Received stop request via API.")
    # Schedule the shutdown to happen shortly after responding
    background_tasks.add_task(shutdown_server)
    return {"status": "stopping", "message": "Server is shutting down..."}

@app.post("/api/reset")
async def factory_reset(background_tasks: BackgroundTasks):
    """
    Performs a factory reset (wipes DB, Logs, Downloads) and shuts down.
    """
    from email_archiver.core.utils import perform_reset
    
    logging.warning("⚠️ Received FACTORY RESET request via API.")
    
    try:
        deleted_items = perform_reset()
        logging.info(f"Factory reset successful. Deleted: {deleted_items}")
        
        # Shutdown is required because DB/Logs are gone
        background_tasks.add_task(shutdown_server)
        
        return {
            "status": "success", 
            "message": "Factory reset complete. Server is shutting down.",
            "deleted": deleted_items
        }
    except Exception as e:
        logging.error(f"Factory reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
@app.post("/api/sync")
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    if sync_status["is_running"]:
        return {"message": "Sync already in progress"}
    
    background_tasks.add_task(
        run_sync_task, 
        request.provider, 
        request.incremental, 
        request.classify, 
        request.extract,
        request.rename,
        request.embed,
        request.since,
        request.after_id,
        request.specific_id,
        request.query,
        request.llm_base_url,
        request.llm_api_key,
        request.llm_model,
        request.local_only
    )
    return {"message": "Sync started"}

@app.post("/api/sync/stop")
async def stop_sync():
    """Signals the running sync task to stop."""
    global sync_status
    if sync_status["is_running"]:
        sync_status["is_cancelled"] = True
        logging.info("Cancellation requested by user.")
        return {"message": "Cancellation requested"}
    return {"message": "No sync is running"}

@app.get("/api/status")
async def get_status():
    return sync_status

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def start_server(host="127.0.0.1", port=8000, open_browser=False):
    import uvicorn
    import webbrowser
    from threading import Timer

    def launch_browser():
        webbrowser.open(f"http://{host}:{port}")

    try:
        if open_browser:
            Timer(1.5, launch_browser).start()
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        # Silently exit on Ctrl+C
        pass
    finally:
        logging.info("Server stopped.")
