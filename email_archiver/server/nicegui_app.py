"""
NiceGUI-based Web Dashboard for Email Archiver
Migrated from Alpine.js/FastAPI to NiceGUI for better UX and real-time updates.
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field

import yaml
from urllib.parse import quote
from nicegui import ui, app, Client
from fastapi import HTTPException
from fastapi.responses import FileResponse

# Import core logic
from email_archiver.core.db_handler import DBHandler
from email_archiver.core.classifier import EmailClassifier
from email_archiver.core.paths import (
    get_config_path,
    get_auth_dir,
    get_data_dir,
    resolve_path
)
from email_archiver import __version__

# Configuration
CONFIG_PATH = get_config_path()

# Global state
@dataclass
class AppState:
    """Reactive application state"""
    is_running: bool = False
    is_cancelled: bool = False
    last_run: Optional[str] = None
    progress: int = 0
    logs: List[str] = field(default_factory=list)
    
    # Auth status
    gmail_connected: bool = False
    m365_connected: bool = False
    
    # Stats
    total_archived: int = 0
    classified: int = 0
    extracted: int = 0
    last_updated_db: Optional[str] = None
    categories: Dict[str, int] = field(default_factory=dict)
    
    # AI Stats
    ai_classification_success: int = 0
    ai_classification_total: int = 0
    ai_extraction_success: int = 0
    ai_extraction_total: int = 0
    
    # LLM status
    llm_status: str = "checking"
    llm_message: str = ""
    llm_model: str = ""
    ui_theme: str = "dark"

state = AppState()
db = DBHandler()


@app.get("/api/status")
async def get_status():
    """Returns the current sync status for compatibility."""
    return {
        "is_running": state.is_running,
        "is_cancelled": state.is_cancelled,
        "last_run": state.last_run,
        "progress": state.progress,
        "logs": state.logs[-100:] # Return last 100 logs
    }

@app.get("/api/ai-stats")
async def get_ai_stats():
    """Returns AI processing statistics."""
    return db.get_ai_stats()

@app.get("/api/llm-status")
async def get_llm_status():
    """Returns current LLM health status."""
    return {
        "status": state.llm_status,
        "message": state.llm_message,
        "model": state.llm_model
    }


@app.get("/api/emails/{message_id}/download")
async def download_email(message_id: str):
    """Downloads the raw .eml file for an email."""
    email = db.get_email(message_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    file_path = email.get("file_path")
    if not file_path:
         raise HTTPException(status_code=404, detail="File path not recorded for this email")

    try:
        abs_path = resolve_path(file_path)
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error resolving file path: {e}")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Email file not found on disk")
        
    return FileResponse(
        path=abs_path, 
        filename=os.path.basename(abs_path), 
        media_type='message/rfc822'
    )


# Custom log handler for UI
class UILogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        state.logs.append(log_entry)
        if len(state.logs) > 100:
            state.logs.pop(0)

ui_log_handler = UILogHandler()
ui_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))


def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not os.path.exists(path):
        return {
            'app': {'download_dir': 'downloads/', 'ui_theme': 'dark'},
            'gmail': {'scopes': ['https://www.googleapis.com/auth/gmail.readonly']},
            'm365': {'scopes': ['https://graph.microsoft.com/Mail.Read']},
            'classification': {'enabled': False, 'model': 'gpt-4o-mini', 'api_key': '', 'base_url': ''},
            'extraction': {'enabled': False},
            'webhook': {'enabled': False, 'url': '', 'headers': {'Authorization': ''}}
        }
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def save_config(path: str, config: Dict[str, Any]):
    """Save configuration to YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)


def check_auth_status():
    """Check provider authentication status."""
    auth_dir = get_auth_dir()
    state.gmail_connected = os.path.exists(auth_dir / 'gmail_token.json')
    state.m365_connected = os.path.exists(auth_dir / 'm365_token.json')


def refresh_stats():
    """Refresh statistics from database."""
    stats = db.get_stats()
    state.total_archived = stats.get('total_archived', 0)
    state.classified = stats.get('classified', 0)
    state.extracted = stats.get('extracted', 0)
    state.last_updated_db = stats.get('last_updated')
    state.categories = stats.get('categories', {})
    
    # Get AI stats
    ai_stats = db.get_ai_stats()
    state.ai_classification_success = ai_stats.get('classification', {}).get('success', 0)
    state.ai_classification_total = ai_stats.get('classification', {}).get('total', 0)
    state.ai_extraction_success = ai_stats.get('extraction', {}).get('success', 0)
    state.ai_extraction_total = ai_stats.get('extraction', {}).get('total', 0)


def check_llm_status():
    """Check LLM health status."""
    if state.is_running:
        state.llm_status = "checking"
        state.llm_message = "Sync in progress"
        return
    
    try:
        config = load_config(CONFIG_PATH)
        classifier = EmailClassifier(config)
        
        if not classifier.enabled:
            state.llm_status = "disabled"
            state.llm_message = "AI classification not enabled"
            return
        
        is_healthy = classifier.check_health()
        if is_healthy:
            state.llm_status = "online"
            state.llm_message = f"Connected to {classifier.base_url or 'OpenAI'}"
            state.llm_model = classifier.model
        else:
            state.llm_status = "offline"
            state.llm_message = "LLM unreachable"
    except Exception as e:
        state.llm_status = "error"
        state.llm_message = str(e)


# ============================================================================ 
# SYNC OPERATIONS
# ============================================================================ 

async def run_sync_task(
    provider: str,
    incremental: bool = True,
    classify: bool = False,
    extract: bool = False,
    rename: bool = False,
    embed: bool = False,
    since: Optional[str] = None,
    after_id: Optional[str] = None,
    specific_id: Optional[str] = None,
    query: Optional[str] = None,
    local_only: bool = False,
    on_complete: Optional[Callable] = None
):
    """Run synchronization task in background."""
    state.is_running = True
    state.is_cancelled = False
    state.progress = 0
    state.logs = []
    
    root_logger = logging.getLogger()
    root_logger.addHandler(ui_log_handler)
    
    try:
        logging.info(f"Initiating sync for provider: {provider}")
        from email_archiver.main import run_archiver_logic
        
        config = load_config(CONFIG_PATH)
        llm_base_url = config.get('classification', {}).get('base_url')
        llm_api_key = config.get('classification', {}).get('api_key')
        llm_model = config.get('classification', {}).get('model')
        
        await asyncio.to_thread(
            run_archiver_logic,
            provider, incremental, classify, extract,
            since, after_id, specific_id, query,
            rename, embed, llm_api_key, llm_model, llm_base_url, local_only
        )
        
        logging.info("Synchronization completed successfully.")
        state.last_run = datetime.now().isoformat()
        try:
            ui.notify('Sync completed successfully!', type='positive')
        except RuntimeError:
            logging.warning("Skipped UI notification (client disconnected)")
    except Exception as e:
        logging.error(f"Synchronization failed: {e}")
        try:
            ui.notify(f'Sync failed: {e}', type='negative')
        except RuntimeError:
            logging.warning("Skipped failure notification (client disconnected)")
    finally:
        state.is_running = False
        state.progress = 100
        root_logger.removeHandler(ui_log_handler)
        # refresh_stats() handled by auto-refresh timer
        if on_complete:
            try:
                on_complete()
            except Exception as e:
                logging.warning(f"Failed to execute on_complete callback: {e}")


def stop_sync():
    """Stop running sync."""
    if state.is_running:
        state.is_cancelled = True
        logging.info("Cancellation requested by user.")
        ui.notify('Stopping sync...', type='warning')


# ============================================================================ 
# UI COMPONENTS
# ============================================================================ 

def create_stat_card(title: str, value: int, icon: str, color: str = 'primary'):
    """Create a statistics card."""
    with ui.card().classes('w-full'):
        with ui.row().classes('w-full justify-between items-start'):
            ui.label(title).classes('text-xs font-medium text-gray-400 uppercase tracking-wider')
            ui.label(icon).classes('text-2xl')
        ui.label(f'{value:,}').classes(f'text-3xl font-bold text-{color}')


def create_sync_button():
    """Create the main sync button."""
    with ui.card().classes('w-full p-6'):
        ui.label('Synchronization Engine').classes('text-lg font-bold mb-4')
        
        with ui.row().classes('w-full gap-8 items-start'):
            # --- LEFT COLUMN: Configuration ---
            with ui.column().classes('flex-1 gap-6'):
                
                # Row 1: Provider & Switches
                with ui.row().classes('w-full items-center gap-6'):
                    sync_provider = ui.select(
                        ['gmail', 'm365'],
                        value='gmail',
                        label='Provider'
                    ).props('outlined dense options-dense').classes('w-40')
                    
                    with ui.row().classes('flex-1 gap-4 items-center'):
                        sync_incremental = ui.switch('Incremental', value=True).props('dense color=blue')
                        with sync_incremental:
                            ui.tooltip('Only fetch new emails since last sync. Much faster!')
                            
                        sync_classify = ui.switch('Classify', value=True).props('dense color=green')
                        with sync_classify:
                            ui.tooltip('Use AI to categorize emails (e.g. Finance, Travel, Work).')
                            
                        sync_extract = ui.switch('Extract', value=True).props('dense color=purple')
                        with sync_extract:
                            ui.tooltip('Deep-scan bodies for entities like organizations and action items.')
                            
                        sync_rename = ui.switch('Rename', value=True).props('dense color=orange')
                        with sync_rename:
                            ui.tooltip('Rename .eml files to clean, slugified titles.')
                            
                        sync_embed = ui.switch('Embed', value=True).props('dense color=cyan')
                        with sync_embed:
                            ui.tooltip('Inject AI metadata directly into the .eml file headers.')

                # Row 2: Input Grid (2x2)
                with ui.grid(columns=2).classes('w-full gap-4'):
                    sync_since = ui.input(
                        'Since Date',
                        value=datetime.now().strftime('%Y-%m-%d')
                    ).props('outlined dense type=date').classes('w-full')
                    with sync_since:
                        ui.tooltip('Fetch emails received on or after this date.')
                    
                    sync_query = ui.input(
                        'Search Query',
                        placeholder='e.g. from:invoice'
                    ).props('outlined dense').classes('w-full')
                    with sync_query:
                        ui.tooltip('Advanced search query (e.g. "subject:report").')
                    
                    sync_after_id = ui.input(
                        'After ID',
                        placeholder='Fetch emails after this ID'
                    ).props('outlined dense').classes('w-full')
                    with sync_after_id:
                        ui.tooltip('Resume fetching precisely after this unique Message ID.')
                    
                    sync_specific_id = ui.input(
                        'Specific ID',
                        placeholder='Fetch only this specific email'
                    ).props('outlined dense').classes('w-full')
                    with sync_specific_id:
                        ui.tooltip('Download only this single message by ID (overrides other filters).')
            
            # --- RIGHT COLUMN: Action Buttons ---
            with ui.column().classes('items-center gap-4 min-w-[140px] pt-1'):
                @ui.refreshable
                def sync_button_display():
                    def on_sync_click():
                        if state.is_running:
                            stop_sync()
                        else:
                            asyncio.create_task(run_sync_task(
                                provider=sync_provider.value,
                                incremental=sync_incremental.value,
                                classify=sync_classify.value,
                                extract=sync_extract.value,
                                rename=sync_rename.value,
                                embed=sync_embed.value,
                                since=sync_since.value if sync_since.value else None,
                                after_id=sync_after_id.value if sync_after_id.value else None,
                                specific_id=sync_specific_id.value if sync_specific_id.value else None,
                                query=sync_query.value if sync_query.value else None,
                                on_complete=lambda: (sync_button_display.refresh(), reanalyze_button.refresh())
                            ))
                        sync_button_display.refresh()
                        reanalyze_button.refresh()
                    
                    btn_text = 'STOP' if state.is_running else 'SYNC'
                    btn_color = 'red' if state.is_running else 'primary'
                    ui.button(btn_text, on_click=on_sync_click).classes(f'w-32 h-32 rounded-full bg-{btn_color} text-xl font-bold shadow-lg')
                
                sync_button_display()
                
                # Re-analyze button
                @ui.refreshable
                def reanalyze_button():
                    if not state.is_running:
                        def on_reanalyze():
                            asyncio.create_task(run_sync_task(
                                provider=sync_provider.value,
                                incremental=False,
                                classify=sync_classify.value,
                                extract=sync_extract.value,
                                rename=sync_rename.value,
                                embed=sync_embed.value,
                                local_only=True,
                                on_complete=lambda: (sync_button_display.refresh(), reanalyze_button.refresh())
                            ))
                            sync_button_display.refresh()
                            reanalyze_button.refresh()
                        
                        ui.button('Re-analyze Local Archive', on_click=on_reanalyze).props('flat dense size=sm').classes('text-gray-400 hover:text-white')
                
                reanalyze_button()


def create_log_console():
    """Create the real-time log console."""
    with ui.card().classes('w-full h-56'):
        ui.label('Process Output').classes('text-xs font-bold text-gray-400 uppercase mb-2')
        
        log_container = ui.column().classes('w-full h-40 overflow-y-auto font-mono text-xs bg-gray-900 rounded p-2')
        
        def update_logs():
            log_container.clear()
            with log_container:
                if not state.logs:
                    ui.label('System idle. Waiting for task initiation...').classes('text-gray-500 italic')
                else:
                    for log in state.logs[-50:]:
                        color = 'text-red-400' if 'ERROR' in log else 'text-yellow-400' if 'WARNING' in log else 'text-gray-300'
                        ui.label(log).classes(f'{color} text-xs')
            
            # Auto-scroll to bottom
            ui.run_javascript(f'''
                const container = document.querySelector('.overflow-y-auto');
                if (container) container.scrollTop = container.scrollHeight;
            ''')
        
        ui.timer(1.0, update_logs)


def create_email_table():
    """Create the email intelligence feed table."""
    with ui.card().classes('w-full glass'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label('Intelligence Feed').classes('text-lg font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent')
            
            # Search input
            search_input = ui.input('Search', placeholder='Search emails...') \
                .props('outlined dense').classes('w-64')
            with search_input.add_slot('prepend'):
                ui.icon('search')
            
        # Pagination state
        current_page = {'value': 1}
        page_size = 20
        search_query = {'value': ''}
        
        # Store email data for access in handlers
        email_data = {'emails': []}
        
        @ui.refreshable
        def email_table_display():
            # Calculate offset
            offset = (current_page['value'] - 1) * page_size
            
            # Get total count first
            count = db.get_email_count(search_query['value'] if search_query['value'] else None)
            total_pages = (count + page_size - 1) // page_size
            if total_pages < 1: total_pages = 1
            
            # Get emails with search
            emails = db.get_emails(
                limit=page_size,
                offset=offset,
                search_query=search_query['value'] if search_query['value'] else None
            )
            
            # Store emails for handlers (though we use direct lambda binding now)
            email_data['emails'] = {email.get('message_id'): email for email in emails}
            
            # Custom List View
            # Header
            with ui.row().classes('w-full px-4 py-2 border-b border-white/10 text-xs font-bold text-gray-400 uppercase tracking-wider'):
                ui.label('Subject').classes('flex-1')
                ui.label('From').classes('w-1/4')
                ui.label('Date').classes('w-32')
                ui.label('Category').classes('w-24 text-right pr-4')

            # Rows Container
            with ui.column().classes('w-full gap-0 min-h-[200px]'):
                if not emails:
                    ui.label('No emails found.').classes('w-full text-center text-gray-500 py-8 italic')
                
                for email in emails:
                    # Prepare display data
                    subject = email.get('subject', 'No Subject') or 'No Subject'
                    subject = subject[:60] + '...' if len(subject) > 60 else subject
                    
                    sender = email.get('sender', 'Unknown') or 'Unknown'
                    sender = sender[:30] + '...' if len(sender) > 30 else sender
                    
                    date_str = email.get('received_at', '')[:10] if email.get('received_at') else ''
                    
                    category = 'UNPROCESSED'
                    if email.get('classification'):
                        category = email['classification'].get('category', 'UNPROCESSED').upper()
                    
                    # Row Item
                    with ui.row().classes('w-full px-4 py-3 border-b border-white/5 items-center hover:bg-white/5 transition-colors group'):
                        # Subject (Clickable)
                        ui.label(subject).classes('flex-1 font-medium truncate cursor-pointer hover:text-blue-400 transition-colors').on('click', lambda e=email: show_email_detail(e))
                        
                        # Sender
                        ui.label(sender).classes('w-1/4 text-gray-400 truncate text-xs')
                        
                        # Date
                        ui.label(date_str).classes('w-32 text-gray-500 text-xs')
                        
                        # Category Badge
                        with ui.element('div').classes('w-24 flex justify-end'):
                            color = 'blue' if category != 'UNPROCESSED' else 'gray'
                            ui.label(category).classes(f'text-[10px] px-2 py-0.5 bg-{color}-500/10 text-{color}-400 rounded-full border border-{color}-500/20')

            # Pagination Controls
            with ui.row().classes('w-full justify-between items-center mt-4 px-2'):
                # Info label
                start_idx = offset + 1
                end_idx = min(offset + len(emails), count)
                if count == 0:
                    ui.label('0 items').classes('text-xs text-gray-500')
                else:
                    ui.label(f'Showing {start_idx}-{end_idx} of {count}').classes('text-xs text-gray-500')
                
                # Pagination Component
                if total_pages > 1:
                    def on_page_change(e):
                        current_page['value'] = e.value
                        email_table_display.refresh()
                        
                    ui.pagination(min=1, max=total_pages, value=current_page['value']) \
                        .props('max-pages=5 boundary-numbers') \
                        .on_value_change(on_page_change)
        
        email_table_display()
        
        # Search handler
        def on_search(e):
            search_query['value'] = search_input.value
            current_page['value'] = 1
            email_table_display.refresh()
        
        search_input.on('change', on_search)


def show_email_detail(email: Dict[str, Any]):
    """Show email detail dialog with full information."""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl max-h-[90vh] overflow-hidden'):
        # Header with title and close button
        with ui.row().classes('w-full justify-between items-start p-3 border-b border-white/10'):
            with ui.column().classes('flex-1'):
                ui.label(email.get('subject', 'No Subject')).classes('text-xl font-bold mb-2')
                with ui.row().classes('gap-4 text-xs text-gray-400'):
                    ui.label(f"From: {email.get('sender', 'Unknown')}")
                    ui.label(f"Date: {email.get('received_at', '')[:16] if email.get('received_at') else 'Unknown'}")
                    
                    # Download button in header
                    msg_id = email.get('message_id', '')
                    if msg_id:
                        def download_eml():
                            # Encode ID to handle special characters (like <, >, @) in URL
                            safe_id = quote(msg_id, safe='')
                            ui.download(f'/api/emails/{safe_id}/download')
                            
                        with ui.button(on_click=download_eml).props('flat no-caps dense').classes('flex items-center gap-1 text-blue-400 hover:text-blue-300 ml-4 pl-4 border-l border-white/10'):
                            # Explicitly allow SVG content by disabling sanitization for this trusted icon
                            ui.html('<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>', sanitize=False)
                            ui.label('Download EML').classes('text-xs font-bold')
            
            ui.button(icon='close', on_click=dialog.close).props('flat round').classes('text-gray-400')
        
        # Scrollable content
        with ui.column().classes('flex-1 overflow-y-auto p-6 gap-6'):
            # Intelligence Panel - Side by side
            with ui.row().classes('w-full gap-4'):
                # Classification Panel
                with ui.card().classes('flex-1 bg-blue-900/20 border border-blue-500/20'):
                    ui.label('Classification').classes('text-xs font-bold text-blue-400 uppercase mb-3')
                    
                    if email.get('classification'):
                        cat = email['classification'].get('category', 'Unknown')
                        with ui.row().classes('items-center gap-3 mb-3'):
                            ui.label(cat.upper()).classes('px-3 py-1 bg-blue-500/20 rounded-full text-xs font-bold')
                            if email['classification'].get('reasoning'):
                                ui.label('AI Confidence: High').classes('text-xs text-gray-500')
                        
                        if email['classification'].get('reasoning'):
                            ui.label(email['classification']['reasoning']).classes('text-sm text-gray-300 leading-relaxed')
                    else:
                        ui.label('No AI classification metadata available for this item.').classes('text-xs text-gray-600 italic')
                
                # System Info Panel
                with ui.card().classes('flex-1 bg-purple-900/20 border border-purple-500/20'):
                    ui.label('System Info').classes('text-xs font-bold text-purple-400 uppercase mb-3')
                    
                    with ui.column().classes('gap-3'):
                        with ui.row().classes('justify-between'):
                            ui.label('Source').classes('text-xs text-gray-400 font-bold uppercase')
                            ui.label(email.get('provider', 'Unknown').upper()).classes('text-xs text-gray-300 font-bold')
                        
                        with ui.row().classes('justify-between'):
                            ui.label('Archived').classes('text-xs text-gray-400 font-bold uppercase')
                            archived_date = email.get('processed_at', '')[:16] if email.get('processed_at') else 'Unknown'
                            ui.label(archived_date).classes('text-xs text-gray-300 font-bold')
                        
                        if email.get('file_path'):
                            ui.separator().classes('border-white/5')
                            ui.label('Local Path').classes('text-xs text-gray-400 font-bold uppercase mb-1')
                            ui.label(email['file_path']).classes('text-xs text-indigo-300 font-mono bg-black/20 p-2 rounded break-all')
            
            # Extraction Results
            if email.get('extraction'):
                with ui.card().classes('w-full bg-indigo-900/20 border border-indigo-500/20'):
                    ui.label('Deep Extraction Results').classes('text-xs font-bold text-indigo-400 uppercase mb-4')
                    
                    with ui.column().classes('gap-6'):
                        # Summary
                        if email['extraction'].get('summary'):
                            ui.label('Summary').classes('text-xs text-gray-400 font-bold uppercase mb-1')
                            ui.label(email['extraction']['summary']).classes('text-sm text-gray-200 leading-relaxed')
                        
                        # Action Items and Organizations side by side
                        with ui.row().classes('w-full gap-6'):
                            # Action Items
                            if email['extraction'].get('action_items'):
                                with ui.column().classes('flex-1'):
                                    ui.label('Action Items').classes('text-xs text-gray-400 font-bold uppercase mb-2')
                                    for item in email['extraction']['action_items']:
                                        with ui.row().classes('gap-2'):
                                            ui.label('▹').classes('text-indigo-500')
                                            ui.label(item).classes('text-xs text-gray-400')
                            
                            # Organizations/Entities
                            if email['extraction'].get('organizations'):
                                with ui.column().classes('flex-1'):
                                    ui.label('Relevant Entities').classes('text-xs text-gray-400 font-bold uppercase mb-2')
                                    with ui.row().classes('flex-wrap gap-2'):
                                        for org in email['extraction']['organizations']:
                                            ui.label(org).classes('px-2 py-1 bg-white/5 rounded text-xs text-gray-400')
                            
                            # People (if available)
                            if email['extraction'].get('people'):
                                with ui.column().classes('flex-1'):
                                    ui.label('People Mentioned').classes('text-xs text-gray-400 font-bold uppercase mb-2')
                                    with ui.row().classes('flex-wrap gap-2'):
                                        for person in email['extraction']['people']:
                                            ui.label(person).classes('px-2 py-1 bg-white/5 rounded text-xs text-gray-400')
    
    dialog.open()


def create_settings_page(dark_mode: ui.dark_mode):
    """Create the settings page with a modern 2-column layout."""
    config = load_config(CONFIG_PATH)
    
    # Ensure nested dicts exist
    if 'app' not in config:
        config['app'] = {'download_dir': 'downloads/', 'ui_theme': 'dark'}
    if 'classification' not in config:
        config['classification'] = {'enabled': False, 'model': 'gpt-4o-mini', 'api_key': '', 'base_url': ''}
    if 'extraction' not in config:
        config['extraction'] = {'enabled': False}
    if 'webhook' not in config:
        config['webhook'] = {'enabled': False, 'url': '', 'headers': {'Authorization': ''}}
    if 'headers' not in config['webhook']:
        config['webhook']['headers'] = {'Authorization': ''}

    def apply_theme(mode: str):
        """Apply theme mode to the UI."""
        if mode == 'dark':
            dark_mode.enable()
        elif mode == 'light':
            dark_mode.disable()
        else:
            dark_mode.auto()

    # --- SAVE HANDLER ---
    def save_settings():
        config['app']['download_dir'] = download_dir.value
        config['app']['ui_theme'] = theme_mode.value
        state.ui_theme = theme_mode.value
        
        # Ensure applied
        apply_theme(state.ui_theme)
            
        config['classification']['enabled'] = class_enabled.value
        config['classification']['model'] = llm_model.value
        config['classification']['api_key'] = llm_api_key.value
        config['classification']['base_url'] = llm_base_url.value
        config['extraction']['enabled'] = extract_enabled.value
        config['webhook']['enabled'] = webhook_enabled.value
        config['webhook']['url'] = webhook_url.value
        config['webhook']['headers']['Authorization'] = webhook_secret.value
        
        save_config(CONFIG_PATH, config)
        ui.notify('Settings saved successfully!', type='positive')

    # --- UI LAYOUT ---
    with ui.row().classes('w-full gap-6 items-start'):
        
        # === LEFT COLUMN: App & Intelligence ===
        with ui.column().classes('flex-1 gap-6'):
            
            # 1. System Settings
            with ui.card().classes('w-full p-4'):
                ui.label('System Preferences').classes('text-lg font-bold mb-2')
                
                with ui.row().classes('w-full gap-4'):
                    download_dir = ui.input(
                        'Download Directory',
                        value=config['app'].get('download_dir', 'downloads/')
                    ).props('outlined dense').classes('flex-1')
                    
                    theme_mode = ui.select(
                        {'dark': 'Dark', 'light': 'Light', 'system': 'System'},
                        value=config['app'].get('ui_theme', 'dark'),
                        label='Theme',
                        on_change=lambda e: apply_theme(e.value)
                    ).props('outlined dense options-dense').classes('w-32')
                    with theme_mode:
                        ui.tooltip('Switch between Dark, Light, or System-based appearance.')

            # 2. Intelligence Hub
            with ui.card().classes('w-full p-4'):
                with ui.row().classes('w-full justify-between items-center mb-4'):
                    ui.label('Intelligence Hub').classes('text-lg font-bold')
                    ui.icon('psychology', size='md').classes('text-purple-400')
                
                # Toggles
                with ui.row().classes('w-full gap-4 mb-4'):
                    class_enabled = ui.switch('Classification', value=config['classification'].get('enabled', False)).props('dense color=blue')
                    with class_enabled:
                        ui.tooltip('Enable AI-powered categorization of your emails.')
                        
                    extract_enabled = ui.switch('Extraction', value=config['extraction'].get('enabled', False)).props('dense color=purple')
                    with extract_enabled:
                        ui.tooltip('Enable deep extraction of structured data from email bodies.')
                
                ui.separator().classes('mb-4')
                
                # LLM Config
                ui.label('LLM Configuration').classes('text-sm font-bold text-gray-400 mb-2')
                
                # Presets
                with ui.row().classes('gap-2 mb-3'):
                    def set_preset(preset: str):
                        if preset == 'openai':
                            llm_base_url.value = ''
                            llm_model.value = 'gpt-4o-mini'
                        elif preset == 'ollama':
                            llm_base_url.value = 'http://localhost:11434/v1'
                            llm_model.value = 'llama3'
                        elif preset == 'lm_studio':
                            llm_base_url.value = 'http://localhost:1234/v1'
                            llm_model.value = 'model-identifier'
                    
                    ui.button('OpenAI', on_click=lambda: set_preset('openai')).props('flat dense size=sm').classes('bg-green-500/10 text-green-400')
                    ui.button('Ollama', on_click=lambda: set_preset('ollama')).props('flat dense size=sm').classes('bg-orange-500/10 text-orange-400')
                    ui.button('LM Studio', on_click=lambda: set_preset('lm_studio')).props('flat dense size=sm').classes('bg-blue-500/10 text-blue-400')

                # Fields
                llm_model = ui.input('Model Name', value=config['classification'].get('model', 'gpt-4o-mini')).props('outlined dense').classes('w-full mb-2')
                llm_api_key = ui.input('API Key', value=config['classification'].get('api_key', ''), password=True).props('outlined dense').classes('w-full mb-2')
                llm_base_url = ui.input('Base URL', value=config['classification'].get('base_url', ''), placeholder='Optional (for local LLMs)').props('outlined dense').classes('w-full')

            # 3. Webhooks
            with ui.card().classes('w-full p-4'):
                ui.label('Webhook Notifications').classes('text-lg font-bold mb-4')
                
                webhook_enabled = ui.switch('Enable Webhooks', value=config['webhook'].get('enabled', False)).props('dense color=green').classes('mb-2')
                webhook_url = ui.input('Endpoint URL', value=config['webhook'].get('url', '')).props('outlined dense').classes('w-full mb-2')
                webhook_secret = ui.input('Auth Secret', value=config['webhook']['headers'].get('Authorization', ''), password=True).props('outlined dense').classes('w-full')

            # Save Actions
            with ui.row().classes('w-full justify-end gap-4 mt-2'):
                ui.button('Discard Changes', on_click=lambda: ui.navigate.reload()).props('flat text-color=gray')
                ui.button('Save Settings', on_click=save_settings).props('unelevated color=primary')


        # === RIGHT COLUMN: Integrations & Danger ===
        with ui.column().classes('flex-1 gap-6'):
            
            ui.label('Provider Integrations').classes('text-xl font-bold px-1')

            # Provider Cards Logic
            @ui.refreshable
            def provider_cards():
                # --- GMAIL ---
                with ui.card().classes('w-full p-4 border-l-4 border-l-red-500'):
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('mail', size='sm').classes('text-red-500')
                            ui.label('Gmail').classes('text-lg font-bold')
                        
                        status = 'Connected' if state.gmail_connected else 'Disconnected'
                        color = 'green' if state.gmail_connected else 'gray'
                        ui.badge(status, color=color).props('outline')

                    # Connect Action
                    async def connect_gmail():
                        try:
                            # Re-load config to ensure we have latest secrets
                            curr_config = load_config(CONFIG_PATH)
                            from email_archiver.core.gmail_handler import GmailHandler
                            handler = GmailHandler(curr_config)
                            url = handler.get_auth_url()
                            
                            with ui.dialog() as dialog, ui.card():
                                ui.label('Connect Gmail').classes('text-lg font-bold')
                                ui.label('Open this URL to authorize:').classes('text-sm')
                                ui.link(url, url, new_tab=True).classes('text-blue-400 break-all')
                                code_input = ui.input('Paste code here').classes('w-full')
                                async def submit_code():
                                    try:
                                        handler.submit_code(code_input.value)
                                        check_auth_status()
                                        ui.notify('Gmail connected!', type='positive')
                                        dialog.close()
                                        provider_cards.refresh()
                                    except Exception as e:
                                        ui.notify(f'Error: {e}', type='negative')
                                ui.button('Submit', on_click=submit_code)
                            dialog.open()
                        except Exception as e:
                            ui.notify(f'Error: {e} - Did you save credentials?', type='negative')

                    ui.button('Connect / Re-connect', on_click=connect_gmail, icon='link').props('outline size=sm color=red').classes('w-full mb-4')

                    # Credentials Accordion
                    with ui.expansion('Configure Credentials', icon='key').classes('w-full text-sm bg-gray-900/30 rounded'):
                        ui.label('Paste content of credentials.json:').classes('text-xs text-gray-500 mb-1 p-2')
                        gmail_secret = ui.textarea(placeholder='{"installed": ...}').props('filled dense input-style="font-family: monospace; font-size: 10px"').classes('w-full')
                        
                        async def save_gmail_secret():
                            try:
                                if not gmail_secret.value: return
                                json.loads(gmail_secret.value) # Validate
                                auth_dir = get_auth_dir()
                                auth_dir.mkdir(parents=True, exist_ok=True)
                                with open(auth_dir / 'client_secret.json', 'w') as f:
                                    f.write(gmail_secret.value)
                                ui.notify('Gmail credentials saved!', type='positive')
                                gmail_secret.value = ''
                            except Exception as e:
                                ui.notify(f'Error: {e}', type='negative')
                        
                        ui.button('Save JSON', on_click=save_gmail_secret).props('flat dense size=sm').classes('w-full mt-1')

                # --- MICROSOFT 365 ---
                with ui.card().classes('w-full p-4 border-l-4 border-l-blue-500'):
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('cloud', size='sm').classes('text-blue-500')
                            ui.label('Microsoft 365').classes('text-lg font-bold')
                        
                        status = 'Connected' if state.m365_connected else 'Disconnected'
                        color = 'green' if state.m365_connected else 'gray'
                        ui.badge(status, color=color).props('outline')

                    # Connect Action
                    async def connect_m365():
                        try:
                            curr_config = load_config(CONFIG_PATH)
                            from email_archiver.core.graph_handler import GraphHandler
                            handler = GraphHandler(curr_config)
                            flow = handler.initiate_device_flow()
                            
                            with ui.dialog() as dialog, ui.card():
                                ui.label('Connect Microsoft 365').classes('text-lg font-bold')
                                ui.label(flow.get('message', ''))
                                ui.label(flow.get('user_code', '')).classes('text-3xl font-mono font-bold text-blue-400')
                                async def complete_flow():
                                    success = await asyncio.to_thread(handler.complete_device_flow, flow)
                                    if success:
                                        check_auth_status()
                                        ui.notify('M365 connected!', type='positive')
                                        dialog.close()
                                        provider_cards.refresh()
                                    else:
                                        ui.notify('Authentication failed', type='negative')
                                ui.button('I have authenticated', on_click=complete_flow)
                            dialog.open()
                        except Exception as e:
                            ui.notify(f'Error: {e} - Did you save config?', type='negative')

                    ui.button('Connect / Re-connect', on_click=connect_m365, icon='link').props('outline size=sm color=blue').classes('w-full mb-4')

                    # Config Accordion
                    with ui.expansion('Configure Client', icon='key').classes('w-full text-sm bg-gray-900/30 rounded'):
                        ui.label('Paste content of config.json:').classes('text-xs text-gray-500 mb-1 p-2')
                        m365_secret = ui.textarea(placeholder='{"client_id": ...}').props('filled dense input-style="font-family: monospace; font-size: 10px"').classes('w-full')
                        
                        async def save_m365_secret():
                            try:
                                if not m365_secret.value: return
                                json.loads(m365_secret.value) # Validate
                                config_dir = get_config_path().parent
                                config_dir.mkdir(parents=True, exist_ok=True)
                                with open(config_dir / 'client_secret.json', 'w') as f:
                                    f.write(m365_secret.value)
                                ui.notify('M365 config saved!', type='positive')
                                m365_secret.value = ''
                            except Exception as e:
                                ui.notify(f'Error: {e}', type='negative')
                        
                        ui.button('Save JSON', on_click=save_m365_secret).props('flat dense size=sm').classes('w-full mt-1')

            provider_cards()

            # 4. Danger Zone
            with ui.card().classes('w-full p-4 border border-red-900/50 bg-red-900/10'):
                ui.label('Danger Zone').classes('text-lg font-bold text-red-400 mb-2')
                ui.label('Permanently delete all data including database, logs, and downloads.').classes('text-xs text-gray-400 mb-4')
                
                def confirm_reset():
                    with ui.dialog() as dialog, ui.card():
                        ui.label('⚠️ Confirm Factory Reset').classes('text-xl font-bold text-red-400')
                        ui.label('This will PERMANENTLY DELETE all your data. This cannot be undone.').classes('text-sm')
                        with ui.row().classes('justify-end gap-2 mt-4'):
                            ui.button('Cancel', on_click=dialog.close)
                            async def do_reset():
                                from email_archiver.core.utils import perform_reset
                                perform_reset()
                                ui.notify('Factory reset complete. Restarting...', type='warning')
                                dialog.close()
                                await asyncio.sleep(1)
                                app.shutdown()
                            ui.button('Confirm Reset', on_click=do_reset).classes('bg-red-600')
                    dialog.open()
                
                ui.button('Factory Reset', on_click=confirm_reset, icon='delete_forever').props('unelevated color=red').classes('w-full')


# ============================================================================ 
# MAIN PAGE LAYOUT
# ============================================================================ 

@ui.page('/')
def main_page():
    """Main dashboard page."""
    # Initialize state
    check_auth_status()
    refresh_stats()
    check_llm_status()
    
    # Initialize theme from config
    config = load_config(CONFIG_PATH)
    state.ui_theme = config.get('app', {}).get('ui_theme', 'dark')
    
    # Apply theme
    dark_mode = ui.dark_mode()
    if state.ui_theme == 'dark':
        dark_mode.enable()
    elif state.ui_theme == 'light':
        dark_mode.disable()
    else:
        dark_mode.auto()
    
    # Custom CSS - Theme Aware
    ui.add_head_html('''
    <style>
        body { font-family: 'Inter', sans-serif; }
        
        /* Backgrounds */
        .body--dark .nicegui-content { background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%); min-height: 100vh; }
        .body--light .nicegui-content { background: #f5f7fa; min-height: 100vh; }
        
        /* Headers */
        .body--dark .q-header { background-color: #0f0f23 !important; border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important; }
        .body--light .q-header { background-color: #ffffff !important; color: #1a1a2e !important; border-bottom: 1px solid rgba(0, 0, 0, 0.1) !important; }
        
        /* Cards */
        .body--dark .q-card { background: rgba(255, 255, 255, 0.05) !important; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); }
        .body--light .q-card { background: #ffffff !important; border: 1px solid rgba(0, 0, 0, 0.1) !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important; }
        
        /* Tables */
        .q-table { background: transparent !important; }
        .q-table__card { background: transparent !important; }
        
        /* Tab Indicators on edge */
        .q-tab__indicator { height: 3px !important; border-radius: 3px 3px 0 0; }
        .q-tabs { height: 100%; }
        
        /* Light mode text colors */
        .body--light .text-gray-200 { color: #334155 !important; }
        .body--light .text-gray-300 { color: #475569 !important; }
        .body--light .text-gray-400 { color: #64748b !important; }
        .body--light .text-gray-500 { color: #94a3b8 !important; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    ''')
    
    # Header
    with ui.header().classes('p-0'):
        with ui.row().classes('w-full items-center justify-between px-4 h-14'):
            # 1. Logo & Title
            with ui.row().classes('items-center gap-3'):
                # EESA Logo SVG
                ui.html('''
                    <svg width="48" height="48" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <style>
                            .eesa-text { fill: #1e293b; }
                            .eesa-wireframe { stroke: #94a3b8; }
                            @media (prefers-color-scheme: dark) {
                                .eesa-text { fill: #f8fafc; }
                                .eesa-wireframe { stroke: #475569; }
                            }
                        </style>
                        <defs>
                            <linearGradient id="mainGradient" x1="100" y1="100" x2="400" y2="400" gradientUnits="userSpaceOnUse">
                                <stop offset="0%" stop-color="#0ea5e9" />
                                <stop offset="100%" stop-color="#7c3aed" />
                            </linearGradient>
                        </defs>
                        <path d="M128 240 V340 C128 362.091 145.909 380 168 380 H344 C366.091 380 384 362.091 384 340 V240" stroke="url(#mainGradient)" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M150 190 L235 275 C246.7 286.7 265.3 286.7 277 275 L362 190" stroke="url(#mainGradient)" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>
                        <path class="eesa-wireframe" d="M150 190 V152 C150 140 160 130 172 130 H340 C352 130 362 140 362 152 V190" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M390 100 L400 120 L420 130 L400 140 L390 160 L380 140 L360 130 L380 120 Z" fill="#db2777" />
                    </svg>
                ''', sanitize=False).classes('w-12 h-12')
                with ui.column().classes('gap-0'):
                    ui.label('Archive Intelligence').classes('text-sm font-bold leading-tight')
                    ui.label(f'v{__version__}').classes('text-[10px] text-gray-500 leading-tight')
            
            # 2. Navigation Tabs (Moved to Header)
            with ui.tabs().classes('bg-transparent text-gray-400 self-stretch') \
                .props('indicator-color="blue-400" active-color="blue-400" dense no-caps') as tabs:
                dashboard_tab = ui.tab('Dashboard', icon='dashboard')
                settings_tab = ui.tab('Settings', icon='settings')

            # 3. Status indicator
            @ui.refreshable
            def status_indicator():
                with ui.row().classes('items-center gap-2 px-4 py-2 bg-white/5 rounded-xl'):
                    if state.is_running:
                        ui.element('div').classes('w-2 h-2 rounded-full bg-green-400 animate-pulse')
                        ui.label('SYNC ACTIVE').classes('text-xs font-bold uppercase text-green-400')
                    else:
                        ui.element('div').classes('w-2 h-2 rounded-full bg-gray-500')
                        ui.label('READY').classes('text-xs font-bold uppercase text-gray-400')
            
            status_indicator()
    
    # Main content panels
    with ui.tab_panels(tabs, value=dashboard_tab).classes('w-full flex-1 bg-transparent'):
        # Dashboard Panel
        with ui.tab_panel(dashboard_tab).classes('p-4'):
            # Welcome wizard container
            welcome_card = ui.card().classes('w-full bg-blue-900/20 border-blue-500/20 mb-4')
            
            with welcome_card:
                with ui.row().classes('items-center gap-8'):
                    with ui.column().classes('flex-1'):
                        ui.label('Welcome to Email Archiver').classes('text-2xl font-bold')
                        ui.label('Connect your first email provider to start building your intelligence archive.').classes('text-gray-400')
                        with ui.row().classes('gap-4 mt-4'):
                            ui.button('Connect Gmail', on_click=lambda: tabs.set_value(settings_tab))
                            ui.button('Connect Microsoft 365', on_click=lambda: tabs.set_value(settings_tab))
                    ui.label('🚀').classes('text-6xl')
            
            # Stats grid
            @ui.refreshable
            def stats_grid():
                with ui.row().classes('w-full gap-4'):
                    with ui.card().classes('flex-1'):
                        ui.label('TOTAL ARCHIVED').classes('text-xs text-gray-400 uppercase')
                        ui.label(f'{state.total_archived:,}').classes('text-3xl font-bold')
                        
                        # Last updated timestamp
                        last_ts = state.last_updated_db or state.last_run
                        ts_display = "Never"
                        if last_ts:
                            try:
                                # Handle ISO format
                                dt = datetime.fromisoformat(last_ts)
                                ts_display = dt.strftime('%Y-%m-%d %H:%M')
                            except:
                                ts_display = str(last_ts)
                        
                        ui.label(f'Updated: {ts_display}').classes('text-xs text-gray-500')
                    
                    with ui.card().classes('flex-1'):
                        ui.label('AI CLASSIFIED').classes('text-xs text-gray-400 uppercase')
                        ui.label(f'{state.classified:,}').classes('text-3xl font-bold')
                        if state.ai_classification_total > 0:
                            success_rate = (state.ai_classification_success / state.ai_classification_total) * 100
                            ui.label(f'Success Rate: {success_rate:.1f}%').classes('text-xs text-green-400')
                        else:
                            ui.label(f'Active Categories: {len(state.categories)}').classes('text-xs text-gray-500')
                    
                    with ui.card().classes('flex-1'):
                        ui.label('DATA ENTITIES').classes('text-xs text-gray-400 uppercase')
                        ui.label(f'{state.extracted:,}').classes('text-3xl font-bold')
                        if state.ai_extraction_total > 0:
                            success_rate = (state.ai_extraction_success / state.ai_extraction_total) * 100
                            ui.label(f'Success Rate: {success_rate:.1f}%').classes('text-xs text-indigo-400')
                        else:
                            ui.label('Structured Extraction').classes('text-xs text-gray-500')
                    
                    with ui.card().classes('flex-1'):
                        ui.label('LLM STATUS').classes('text-xs text-gray-400 uppercase')
                        status_color = 'text-green-400' if state.llm_status == 'online' else 'text-red-400' if state.llm_status in ['offline', 'error'] else 'text-gray-400'
                        ui.label(state.llm_status.upper()).classes(f'text-2xl font-bold {status_color}')
                        ui.label(state.llm_model or 'Click to check').classes('text-xs text-gray-500')
            
            stats_grid()
            
            # Sync console
            create_sync_button()
            create_log_console()
            
            # Email table
            create_email_table()
            
            # Update welcome card visibility
            def update_welcome():
                show_welcome = not state.gmail_connected and not state.m365_connected and state.total_archived == 0
                welcome_card.set_visibility(show_welcome)
            
            update_welcome()
        
        # Settings Panel
        with ui.tab_panel(settings_tab).classes('p-4'):
            create_settings_page(dark_mode)
    
    # Auto-refresh timer with adaptive interval
    def auto_refresh():
        refresh_stats()
        check_auth_status()
        
        if state.is_running:
            # Poll faster during active sync for real-time feel
            refresh_timer.interval = 1.0
        else:
            # Poll slower when idle to save resources
            refresh_timer.interval = 10.0
            check_llm_status()
            
        stats_grid.refresh()
        status_indicator.refresh()
    
    refresh_timer = ui.timer(3.0, auto_refresh)


# ============================================================================ 
# SERVER STARTUP
# ============================================================================ 

def start_nicegui_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = False):
    """Start the NiceGUI server."""
    ui.run(
        host=host,
        port=port,
        title='Email Archiver Dashboard',
        favicon='📧',
        dark=True,
        reload=False,
        show=open_browser
    )


if __name__ in {"__main__", "__mp_main__"}:
    start_nicegui_server(open_browser=True)