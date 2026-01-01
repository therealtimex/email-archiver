"""
NiceGUI-based Web Dashboard for Email Archiver
Migrated from Alpine.js/FastAPI to NiceGUI for better UX and real-time updates.
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

import yaml
from nicegui import ui, app, Client

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

state = AppState()
db = DBHandler()


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
            'app': {'download_dir': 'downloads/'},
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
    local_only: bool = False
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
        ui.notify('Sync completed successfully!', type='positive')
    except Exception as e:
        logging.error(f"Synchronization failed: {e}")
        ui.notify(f'Sync failed: {e}', type='negative')
    finally:
        state.is_running = False
        state.progress = 100
        root_logger.removeHandler(ui_log_handler)
        refresh_stats()


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
        
        with ui.row().classes('w-full gap-4 items-start'):
            # Sync options (define first so they're available in on_sync_click)
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('gap-4'):
                    sync_provider = ui.select(
                        ['gmail', 'm365'],
                        value='gmail',
                        label='Provider'
                    ).classes('w-32')
                    sync_incremental = ui.switch('Incremental', value=True)
                
                with ui.row().classes('gap-4'):
                    sync_classify = ui.switch('AI Classify', value=True)
                    sync_extract = ui.switch('Deep Extract', value=True)
                
                with ui.row().classes('gap-4'):
                    sync_rename = ui.switch('Rename Files', value=True)
                    sync_embed = ui.switch('Embed Metadata', value=True)
                
                with ui.row().classes('gap-4 w-full'):
                    sync_since = ui.input(
                        'Since Date',
                        value=datetime.now().strftime('%Y-%m-%d')
                    ).classes('flex-1')
                    sync_query = ui.input('Search Query', placeholder='e.g. from:invoice').classes('flex-1')
                
                # Advanced options
                with ui.expansion('Advanced Options', icon='tune').classes('w-full'):
                    with ui.column().classes('gap-2'):
                        sync_after_id = ui.input(
                            'After ID',
                            placeholder='Fetch emails after this ID'
                        ).classes('w-full')
                        sync_specific_id = ui.input(
                            'Specific ID',
                            placeholder='Fetch only this specific email'
                        ).classes('w-full')
            
            # Big sync button
            with ui.column().classes('items-center gap-4'):
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
                            ))
                        sync_button_display.refresh()
                        reanalyze_button.refresh()
                    
                    btn_text = 'STOP' if state.is_running else 'SYNC'
                    btn_color = 'red' if state.is_running else 'primary'
                    ui.button(btn_text, on_click=on_sync_click).classes(f'w-32 h-32 rounded-full bg-{btn_color}')
                
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
                                local_only=True
                            ))
                            sync_button_display.refresh()
                            reanalyze_button.refresh()
                        
                        ui.button('Re-analyze Local Archive', on_click=on_reanalyze).classes('text-xs')
                
                reanalyze_button()


def create_log_console():
    """Create the real-time log console."""
    with ui.card().classes('w-full h-64'):
        ui.label('Process Output').classes('text-xs font-bold text-gray-400 uppercase mb-2')
        
        log_container = ui.column().classes('w-full h-48 overflow-y-auto font-mono text-xs bg-gray-900 rounded p-2')
        
        def update_logs():
            log_container.clear()
            with log_container:
                if not state.logs:
                    ui.label('System idle. Waiting for task initiation...').classes('text-gray-500 italic')
                else:
                    for log in state.logs[-50:]:  # Show last 50 logs
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
    with ui.card().classes('w-full'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label('Intelligence Feed').classes('text-lg font-bold')
            
            # Search input
            search_input = ui.input('Search', placeholder='Search emails...').classes('w-64')
            
        # Pagination state
        current_page = {'value': 1}
        page_size = 20
        search_query = {'value': ''}
        
        @ui.refreshable
        def email_table_display():
            # Calculate offset
            offset = (current_page['value'] - 1) * page_size
            
            # Get emails with search
            emails = db.get_emails(
                limit=page_size,
                offset=offset,
                search_query=search_query['value'] if search_query['value'] else None
            )
            
            columns = [
                {'name': 'subject', 'label': 'Subject', 'field': 'subject', 'align': 'left', 'sortable': True},
                {'name': 'sender', 'label': 'From', 'field': 'sender', 'align': 'left', 'sortable': True},
                {'name': 'received_at', 'label': 'Date', 'field': 'received_at', 'align': 'left', 'sortable': True},
                {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'center'},
            ]
            
            rows = []
            for email in emails:
                category = ''
                if email.get('classification'):
                    category = email['classification'].get('category', '')
                rows.append({
                    'message_id': email.get('message_id', ''),
                    'subject': email.get('subject', 'No Subject')[:60],
                    'sender': email.get('sender', 'Unknown')[:40],
                    'received_at': email.get('received_at', '')[:16] if email.get('received_at') else '',
                    'category': category.upper() if category else 'UNPROCESSED',
                    'actions': '👁️ View'
                })
            
            email_table = ui.table(
                columns=columns,
                rows=rows,
                row_key='message_id',
                pagination=page_size
            ).classes('w-full')
            
            # Add click handler using selection
            email_table.props('dense')
            
            # Use on_select instead of rowClick
            def on_select(e):
                if e.selection:
                    msg_id = e.selection[0]['message_id']
                    email = db.get_email(msg_id)
                    if email:
                        show_email_detail(email)
                    # Clear selection after opening modal
                    email_table.selected = []
            
            email_table.on('selection', on_select)
            email_table.props('selection="single"')
        
        email_table_display()
        
        # Pagination controls
        with ui.row().classes('w-full justify-between items-center mt-4'):
            def prev_page():
                if current_page['value'] > 1:
                    current_page['value'] -= 1
                    email_table_display.refresh()
            
            def next_page():
                current_page['value'] += 1
                email_table_display.refresh()
            
            def jump_to_page():
                try:
                    page = int(page_jump.value)
                    if page > 0:
                        current_page['value'] = page
                        email_table_display.refresh()
                except ValueError:
                    ui.notify('Invalid page number', type='negative')
            
            ui.button('Previous', on_click=prev_page)
            
            with ui.row().classes('gap-2 items-center'):
                ui.label('Page')
                ui.label(str(current_page['value'])).classes('font-bold')
                ui.label('Jump to:')
                page_jump = ui.input(placeholder='#').classes('w-16')
                ui.button('Go', on_click=jump_to_page)
            
            ui.button('Next', on_click=next_page)
        
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
        with ui.row().classes('w-full justify-between items-start p-4 border-b border-white/10'):
            with ui.column().classes('flex-1'):
                ui.label(email.get('subject', 'No Subject')).classes('text-xl font-bold mb-2')
                with ui.row().classes('gap-4 text-xs text-gray-400'):
                    ui.label(f"From: {email.get('sender', 'Unknown')}")
                    ui.label(f"Date: {email.get('received_at', '')[:16] if email.get('received_at') else 'Unknown'}")
                    
                    # Download button in header
                    msg_id = email.get('message_id', '')
                    if msg_id:
                        download_url = f'/api/emails/{msg_id}/download'
                        with ui.link(download_url, new_tab=False).classes('flex items-center gap-1 text-blue-400 hover:text-blue-300 ml-4 pl-4 border-l border-white/10'):
                            ui.html('<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>')
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


def create_settings_page():
    """Create the settings page."""
    config = load_config(CONFIG_PATH)
    
    # Ensure nested dicts exist
    if 'app' not in config:
        config['app'] = {'download_dir': 'downloads/'}
    if 'classification' not in config:
        config['classification'] = {'enabled': False, 'model': 'gpt-4o-mini', 'api_key': '', 'base_url': ''}
    if 'extraction' not in config:
        config['extraction'] = {'enabled': False}
    if 'webhook' not in config:
        config['webhook'] = {'enabled': False, 'url': '', 'headers': {'Authorization': ''}}
    if 'headers' not in config['webhook']:
        config['webhook']['headers'] = {'Authorization': ''}
    
    with ui.card().classes('w-full'):
        ui.label('System Settings').classes('text-lg font-bold mb-4')
        
        download_dir = ui.input(
            'Download Directory',
            value=config['app'].get('download_dir', 'downloads/')
        ).classes('w-full')
    
    with ui.card().classes('w-full'):
        ui.label('Intelligence Hub').classes('text-lg font-bold mb-4')
        
        # Classification settings
        with ui.expansion('AI Classification', icon='psychology').classes('w-full'):
            class_enabled = ui.switch(
                'Enable Classification',
                value=config['classification'].get('enabled', False)
            )
            
            with ui.row().classes('gap-2 w-full'):
                ui.button('OpenAI', on_click=lambda: set_preset('openai'))
                ui.button('Ollama', on_click=lambda: set_preset('ollama'))
                ui.button('LM Studio', on_click=lambda: set_preset('lm_studio'))
            
            llm_model = ui.input(
                'Model',
                value=config['classification'].get('model', 'gpt-4o-mini')
            ).classes('w-full')
            
            llm_api_key = ui.input(
                'API Key',
                value=config['classification'].get('api_key', ''),
                password=True
            ).classes('w-full')
            
            llm_base_url = ui.input(
                'Base URL',
                value=config['classification'].get('base_url', ''),
                placeholder='Leave empty for OpenAI default'
            ).classes('w-full')
            
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
        
        # Extraction settings
        with ui.expansion('Data Extraction', icon='analytics').classes('w-full'):
            extract_enabled = ui.switch(
                'Enable Extraction',
                value=config['extraction'].get('enabled', False)
            )
    
    # Provider Secrets
    with ui.card().classes('w-full'):
        ui.label('Provider Secrets').classes('text-lg font-bold mb-4')
        
        with ui.expansion('Gmail Credentials', icon='mail').classes('w-full'):
            ui.label('Paste your credentials.json content here').classes('text-sm text-gray-400 mb-2')
            gmail_secret = ui.textarea(
                placeholder='{"installed": {"client_id": "...", ...}}'
            ).classes('w-full font-mono text-xs').props('rows=6')
            
            async def save_gmail_secret():
                try:
                    if not gmail_secret.value:
                        ui.notify('Please enter credentials', type='warning')
                        return
                    
                    # Validate JSON
                    json.loads(gmail_secret.value)
                    
                    # Save to auth directory
                    auth_dir = get_auth_dir()
                    auth_dir.mkdir(parents=True, exist_ok=True)
                    with open(auth_dir / 'client_secret.json', 'w') as f:
                        f.write(gmail_secret.value)
                    
                    ui.notify('Gmail credentials saved!', type='positive')
                    gmail_secret.value = ''
                except json.JSONDecodeError:
                    ui.notify('Invalid JSON format', type='negative')
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')
            
            ui.button('Save Gmail Credentials', on_click=save_gmail_secret).classes('mt-2')
        
        with ui.expansion('Microsoft 365 Config', icon='cloud').classes('w-full'):
            ui.label('Paste your M365 config.json content here').classes('text-sm text-gray-400 mb-2')
            m365_secret = ui.textarea(
                placeholder='{"client_id": "...", "tenant_id": "...", ...}'
            ).classes('w-full font-mono text-xs').props('rows=6')
            
            async def save_m365_secret():
                try:
                    if not m365_secret.value:
                        ui.notify('Please enter config', type='warning')
                        return
                    
                    # Validate JSON
                    json.loads(m365_secret.value)
                    
                    # Save to config directory
                    config_dir = get_config_path().parent
                    config_dir.mkdir(parents=True, exist_ok=True)
                    with open(config_dir / 'client_secret.json', 'w') as f:
                        f.write(m365_secret.value)
                    
                    ui.notify('M365 config saved!', type='positive')
                    m365_secret.value = ''
                except json.JSONDecodeError:
                    ui.notify('Invalid JSON format', type='negative')
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')
            
            ui.button('Save M365 Config', on_click=save_m365_secret).classes('mt-2')
    
    with ui.card().classes('w-full'):
        ui.label('Webhook Notification').classes('text-lg font-bold mb-4')
        
        webhook_enabled = ui.switch(
            'Enable Webhooks',
            value=config['webhook'].get('enabled', False)
        )
        
        webhook_url = ui.input(
            'Endpoint URL',
            value=config['webhook'].get('url', '')
        ).classes('w-full')
        
        webhook_secret = ui.input(
            'Authorization Secret',
            value=config['webhook']['headers'].get('Authorization', ''),
            password=True
        ).classes('w-full')
    
    # Save button
    def save_settings():
        config['app']['download_dir'] = download_dir.value
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
    
    with ui.row().classes('w-full justify-end gap-2 mt-4'):
        ui.button('Discard', on_click=lambda: ui.navigate.reload())
        ui.button('Save Changes', on_click=save_settings).classes('bg-blue-600')


def create_auth_section():
    """Create authentication section."""
    @ui.refreshable
    def auth_cards():
        with ui.card().classes('w-full'):
            ui.label('Provider Connections').classes('text-lg font-bold mb-4')
            
            with ui.row().classes('gap-4'):
                # Gmail
                with ui.card().classes('flex-1'):
                    with ui.row().classes('justify-between items-center'):
                        ui.label('Gmail').classes('font-bold')
                        gmail_status = '✅ Connected' if state.gmail_connected else '❌ Disconnected'
                        ui.label(gmail_status).classes('text-sm')
                    
                    async def connect_gmail():
                        try:
                            config = load_config(CONFIG_PATH)
                            from email_archiver.core.gmail_handler import GmailHandler
                            handler = GmailHandler(config)
                            url = handler.get_auth_url()
                            
                            with ui.dialog() as dialog, ui.card():
                                ui.label('Connect Gmail').classes('text-lg font-bold')
                                ui.label('Open this URL to authorize:').classes('text-sm')
                                ui.link(url, url, new_tab=True).classes('text-blue-400 break-all')
                                
                                code_input = ui.input('Paste authorization code here').classes('w-full')
                                
                                async def submit_code():
                                    try:
                                        handler.submit_code(code_input.value)
                                        check_auth_status()
                                        ui.notify('Gmail connected!', type='positive')
                                        dialog.close()
                                        auth_cards.refresh()
                                    except Exception as e:
                                        ui.notify(f'Error: {e}', type='negative')
                                
                                with ui.row().classes('justify-end gap-2'):
                                    ui.button('Cancel', on_click=dialog.close)
                                    ui.button('Submit', on_click=submit_code)
                            
                            dialog.open()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')
                    
                    ui.button('Connect', on_click=connect_gmail)
                
                # M365
                with ui.card().classes('flex-1'):
                    with ui.row().classes('justify-between items-center'):
                        ui.label('Microsoft 365').classes('font-bold')
                        m365_status = '✅ Connected' if state.m365_connected else '❌ Disconnected'
                        ui.label(m365_status).classes('text-sm')
                    
                    async def connect_m365():
                        try:
                            config = load_config(CONFIG_PATH)
                            from email_archiver.core.graph_handler import GraphHandler
                            handler = GraphHandler(config)
                            flow = handler.initiate_device_flow()
                            
                            with ui.dialog() as dialog, ui.card():
                                ui.label('Connect Microsoft 365').classes('text-lg font-bold')
                                ui.label(flow.get('message', '')).classes('text-sm')
                                ui.label(flow.get('user_code', '')).classes('text-3xl font-mono font-bold text-blue-400')
                                
                                async def complete_flow():
                                    try:
                                        success = await asyncio.to_thread(handler.complete_device_flow, flow)
                                        if success:
                                            check_auth_status()
                                            ui.notify('M365 connected!', type='positive')
                                            dialog.close()
                                            auth_cards.refresh()
                                        else:
                                            ui.notify('Authentication failed', type='negative')
                                    except Exception as e:
                                        ui.notify(f'Error: {e}', type='negative')
                                
                                with ui.row().classes('justify-end gap-2'):
                                    ui.button('Cancel', on_click=dialog.close)
                                    ui.button('Complete', on_click=complete_flow)
                            
                            dialog.open()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')
                    
                    ui.button('Connect', on_click=connect_m365)
    
    auth_cards()


def create_danger_zone():
    """Create danger zone section."""
    with ui.card().classes('w-full border-red-500 border'):
        ui.label('Danger Zone').classes('text-lg font-bold text-red-400 mb-4')
        
        with ui.row().classes('justify-between items-center'):
            with ui.column():
                ui.label('Factory Reset').classes('font-bold')
                ui.label('Permanently delete all data including database, logs, and downloads.').classes('text-sm text-gray-400')
            
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
            
            ui.button('Factory Reset', on_click=confirm_reset).classes('bg-red-600/20 text-red-400')


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
    
    # Dark theme
    ui.dark_mode().enable()
    
    # Custom CSS
    ui.add_head_html('''
    <style>
        body { font-family: 'Inter', sans-serif; }
        .nicegui-content { background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%); min-height: 100vh; }
        .q-card { background: rgba(255, 255, 255, 0.05) !important; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); }
        .q-table { background: transparent !important; }
        .q-table__card { background: transparent !important; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    ''')
    
    # Header
    with ui.header().classes('bg-transparent border-b border-white/10'):
        with ui.row().classes('w-full items-center justify-between px-4'):
            with ui.row().classes('items-center gap-4'):
                ui.label('E').classes('w-10 h-10 bg-blue-600/20 rounded-xl flex items-center justify-center text-blue-400 font-bold')
                with ui.column().classes('gap-0'):
                    ui.label('Archive Intelligence').classes('text-lg font-bold')
                    ui.label(f'Dashboard v{__version__}').classes('text-xs text-gray-400')
            
            # Status indicator
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
    
    # Main content with tabs
    with ui.tabs().classes('w-full') as tabs:
        dashboard_tab = ui.tab('Dashboard', icon='dashboard')
        settings_tab = ui.tab('Settings', icon='settings')
    
    with ui.tab_panels(tabs, value=dashboard_tab).classes('w-full flex-1'):
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
            create_settings_page()
            ui.separator().classes('my-4')
            create_auth_section()
            ui.separator().classes('my-4')
            create_danger_zone()
    
    # Auto-refresh timer
    def auto_refresh():
        refresh_stats()
        check_auth_status()
        if not state.is_running:
            check_llm_status()
        stats_grid.refresh()
        status_indicator.refresh()
    
    ui.timer(3.0, auto_refresh)


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
