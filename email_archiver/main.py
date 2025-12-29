import argparse
import yaml
import json
import os
import sys
import logging
from datetime import datetime
from tqdm import tqdm

from email_archiver.core.utils import (
    setup_logging, 
    generate_filename, 
    send_to_webhook,
    embed_metadata_in_message
)
from email_archiver.core.gmail_handler import GmailHandler
from email_archiver.core.graph_handler import GraphHandler
from email_archiver.core.classifier import EmailClassifier
from email_archiver.core.extractor import EmailExtractor
from email_archiver.core.db_handler import DBHandler
from email_archiver.core.paths import (
    get_config_path, 
    get_data_dir, 
    get_log_path, 
    get_auth_dir, 
    get_download_dir,
    resolve_path,
    get_db_path
)

# Robust path handling
CONFIG_PATH = get_config_path()
# Checkpoint migration path - still defaults to config dir if not found in data root
CHECKPOINT_PATH = resolve_path('config/checkpoint.json')

def load_config(path):
    if not os.path.exists(path):
        # Return a safe default skeleton
        return {
            'app': {'download_dir': 'downloads/'},
            'gmail': {'scopes': ['https://www.googleapis.com/auth/gmail.readonly'], 'client_secrets_file': 'auth/credentials.json'},
            'm365': {'scopes': ['https://graph.microsoft.com/Mail.Read'], 'client_config_file': 'auth/config.json'},
            'classification': {'enabled': False},
            'extraction': {'enabled': False},
            'webhook': {'enabled': False}
        }
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}

def load_checkpoint(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def migrate_checkpoints_to_db(checkpoint_path, db):
    """One-time migration from checkpoint.json to DB."""
    if os.path.exists(checkpoint_path):
        try:
            data = load_checkpoint(checkpoint_path)
            logging.info("Migrating legacy checkpoints to database...")
            if 'gmail' in data and 'last_internal_date' in data['gmail']:
                db.save_checkpoint('gmail', data['gmail']['last_internal_date'])
            if 'm365' in data and 'last_received_time' in data['m365']:
                db.save_checkpoint('m365', data['m365']['last_received_time'])
            # Don't delete JSON yet, but we've indexed it
        except Exception as e:
            logging.error(f"Checkpoint migration failed: {e}")

def save_checkpoint(path, data):
    # Legacy save for safety (optional, but keep for now if needed)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def retry_ai_processing(classify=False, extract=False, llm_api_key=None, llm_model=None, llm_base_url=None, llm_timeout=None):
    """
    Retry AI processing on emails that previously failed.
    """
    config = load_config(CONFIG_PATH)
    db = DBHandler()

    # Get emails that failed AI processing
    failed_emails = db.get_emails_by_ai_status('failed', limit=1000)
    disabled_emails = db.get_emails_by_ai_status('disabled', limit=1000)
    all_retry_emails = failed_emails + disabled_emails

    if not all_retry_emails:
        print("✅ No emails found that need AI retry.")
        return

    print(f"\n📧 Found {len(all_retry_emails)} emails that need AI retry")
    print(f"   - Failed: {len(failed_emails)}")
    print(f"   - Disabled: {len(disabled_emails)}")

    confirm = input("\nProceed with retry? (y/N): ").lower().strip()
    if confirm != 'y':
        print("Retry cancelled.")
        return

    # Setup classification config
    classification_config = config.get('classification', {})
    if classify:
        classification_config['enabled'] = True
    if llm_api_key:
        classification_config['api_key'] = llm_api_key
    if llm_model:
        classification_config['model'] = llm_model
    if llm_base_url:
        classification_config['base_url'] = llm_base_url

    config['classification'] = classification_config
    classifier = EmailClassifier(config)

    # Apply timeout if specified
    if llm_timeout and classifier.enabled:
        classifier.client = openai.OpenAI(
            api_key=classifier.client.api_key,
            base_url=classifier.base_url,
            timeout=llm_timeout
        )

    # Setup extraction config
    extraction_config = config.get('extraction', {})
    if extract:
        extraction_config['enabled'] = True
    config['extraction'] = extraction_config
    extractor = EmailExtractor(config)

    if llm_timeout and extractor.enabled:
        extractor.client = openai.OpenAI(
            api_key=extractor.client.api_key,
            base_url=extractor.base_url,
            timeout=llm_timeout
        )

    # Health checks
    if classifier.enabled:
        classifier.check_health()
    if extractor.enabled:
        extractor.check_health()

    print(f"\n🔄 Starting AI retry for {len(all_retry_emails)} emails...")

    success_count = 0
    failed_count = 0

    for email_data in tqdm(all_retry_emails):
        try:
            # Read the EML file
            file_path = email_data['file_path']
            if not os.path.exists(file_path):
                logging.warning(f"File not found: {file_path}")
                continue

            with open(file_path, 'rb') as f:
                from email import message_from_bytes
                email_obj = message_from_bytes(f.read())

            subject = email_data['subject'] or 'No Subject'
            sender = email_data['sender'] or 'Unknown'
            recipients = email_data['recipients'] or ''

            # Retry classification
            classification = None
            if classifier.enabled:
                classification = classifier.classify_email(email_obj, subject, sender, recipients, '')

            # Retry extraction
            extraction = None
            if extractor.enabled:
                extraction = extractor.extract_metadata(email_obj, subject, sender)

            # Determine new AI status
            ai_classification_status = None
            ai_extraction_status = None
            ai_processing_error = None

            if classifier.enabled or classifier.error_handler.stats['total_calls'] > 0:
                if classification:
                    ai_classification_status = 'success'
                    success_count += 1
                elif classifier.error_handler.is_circuit_open():
                    ai_classification_status = 'disabled'
                    ai_processing_error = classifier.error_handler.circuit_breaker.get('open_reason', 'Unknown')
                    failed_count += 1
                else:
                    ai_classification_status = 'failed'
                    failed_count += 1

            if extractor.enabled or extractor.error_handler.stats['total_calls'] > 0:
                if extraction:
                    ai_extraction_status = 'success'
                elif extractor.error_handler.is_circuit_open():
                    ai_extraction_status = 'disabled'
                    if not ai_processing_error:
                        ai_processing_error = extractor.error_handler.circuit_breaker.get('open_reason', 'Unknown')
                else:
                    ai_extraction_status = 'failed'

            # Update database with new results
            db.record_email(
                message_id=email_data['message_id'],
                provider=email_data['provider'],
                subject=subject,
                sender=sender,
                recipients=recipients,
                received_at=email_data['received_at'],
                file_path=file_path,
                classification=classification,
                extraction=extraction,
                ai_classification_status=ai_classification_status,
                ai_extraction_status=ai_extraction_status,
                ai_processing_error=ai_processing_error
            )

        except Exception as e:
            logging.error(f"Error retrying email {email_data.get('message_id')}: {e}")
            failed_count += 1

    print(f"\n✅ Retry complete!")
    print(f"   - Successful: {success_count}")
    print(f"   - Failed: {failed_count}")

    # Show stats
    if classifier.enabled:
        print(f"\n{classifier.format_stats()}")
    if extractor.enabled:
        print(f"\n{extractor.format_stats()}")

def perform_factory_reset():
    """Wipes all data for a clean slate."""
    from email_archiver.core.utils import perform_reset
    
    print("\n⚠️  FACTORY RESET INITIATED ⚠️")
    print("This will PERMANENTLY DELETE:")
    print(f"  - Database: {get_db_path()}")
    print(f"  - Logs: {get_log_path()}")
    print(f"  - Downloads: {get_download_dir()}")
    print("Authentication tokens in 'auth/' will be PRESERVED.")
    
    confirm = input("\nAre you sure you want to delete ALL data? (y/N): ").lower().strip()
    if confirm != 'y':
        print("Reset cancelled.")
        return

    print("\nDeleting data...")
    deleted = perform_reset()
    
    if deleted:
        print("\n✨ Factory reset complete. You can now start fresh.")
        sys.exit(0)
    else:
        print("\n⚠️  Reset attempted, but no files were deleted (maybe already clean?).")
        sys.exit(1)

def main():
    setup_logging(os.getenv('EESA_LOG_FILE'))
    
    parser = argparse.ArgumentParser(description="Email-to-EML Secure Archiver")
    parser.add_argument('--provider', choices=['gmail', 'm365'], help='Email provider')
    parser.add_argument('--since', help='Download emails since date (YYYY-MM-DD)')
    parser.add_argument('--after-id', help='Download emails received after a specific unique Message ID')
    parser.add_argument('--message-id', help='Download a specific email by its ID (overrides other filters)')
    parser.add_argument('--incremental', action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--query', help='Custom advanced query string')
    # Webhook CLI overrides
    parser.add_argument('--webhook-url', help='Webhook URL to send .eml files to')
    parser.add_argument('--webhook-secret', help='Authorization secret for the webhook (sets Authorization header)')
    # Download directory override
    parser.add_argument('--download-dir', help='Directory to save downloaded .eml files (default: downloads/)')
    # Classification & LLM arguments
    parser.add_argument('--classify', action='store_true', help='Enable AI-powered email classification')
    parser.add_argument('--openai-api-key', help=argparse.SUPPRESS)
    parser.add_argument('--llm-api-key', help='API key for the LLM provider')
    parser.add_argument('--llm-model', help='Model name to use (e.g., gpt-4o-mini, llama3)')
    parser.add_argument('--llm-base-url', help='Base URL for the LLM API')
    parser.add_argument('--skip-promotional', action='store_true', help='Skip promotional emails (requires --classify)')
    parser.add_argument('--extract', action='store_true', help='Enable advanced metadata extraction (v0.5.0+)')
    parser.add_argument('--metadata-output', help='Path to save metadata JSONL file (default: email_metadata.jsonl)')
    parser.add_argument('--rename', action='store_true', help='Intelligently rename .eml files to clean slugs (v0.8.4+)')
    parser.add_argument('--embed', action='store_true', help='Embed AI metadata directly into .eml headers (v0.8.4+)')
    parser.add_argument('--ui', action='store_true', help='Start the web-based dashboard and UI (v0.6.0+)')
    parser.add_argument('--local-only', action='store_true', help='Only process local files and skip remote provider query')
    parser.add_argument('--port', type=int, default=8000, help='Port for the UI dashboard (default: 8000)')
    parser.add_argument('--browser', action='store_true', help='Automatically open browser when starting UI')
    parser.add_argument('--retry-ai', action='store_true', help='Retry AI classification/extraction on emails that previously failed')
    parser.add_argument('--llm-timeout', type=float, help='Timeout in seconds for LLM API calls (default: 60)')
    parser.add_argument('--reset', action='store_true', help='FACTORY RESET: Deletes all data (DB, logs, downloads) to start fresh.')
    
    args = parser.parse_args()

    if args.reset:
        perform_factory_reset()
        return

    # Handle --retry-ai
    if args.retry_ai:
        retry_ai_processing(
            classify=args.classify,
            extract=args.extract,
            llm_api_key=args.llm_api_key,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_timeout=args.llm_timeout
        )
        return

    # Handle UI early
    if args.ui:
        from email_archiver.server.app import start_server
        start_server(port=args.port, open_browser=args.browser)
        return

    if not args.provider:
        parser.error("--provider is required unless using --ui")
    
    config = load_config(CONFIG_PATH)
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    
    try:
        run_archiver_logic_internal(
            provider=args.provider,
            incremental=args.incremental,
            since=args.since,
            after_id=args.after_id,
            specific_id=args.message_id,
            query=args.query,
            classify=args.classify,
            extract=args.extract,
            openai_api_key=args.openai_api_key,
            skip_promotional=args.skip_promotional,
            metadata_output=args.metadata_output,
            llm_base_url=args.llm_base_url,
            llm_api_key=args.llm_api_key,
            llm_model=args.llm_model,
            llm_timeout=args.llm_timeout,
            webhook_url=args.webhook_url,
            webhook_secret=args.webhook_secret,
            download_dir=args.download_dir,
            rename=args.rename,
            embed=args.embed,
            config=config,
            checkpoint=checkpoint,
            local_only=args.local_only
        )
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. Exiting...")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def run_archiver_logic(provider, incremental=True, classify=False, extract=False, since=None, after_id=None, specific_id=None, query=None, rename=False, embed=False, llm_api_key=None, llm_model=None, llm_base_url=None, local_only=False):
    """Entry point for UI to run sync."""
    config = load_config(CONFIG_PATH)
    
    # Basic check - ensure we have either secrets to authenticate OR an existing token
    from email_archiver.core.paths import get_auth_dir
    auth_dir = get_auth_dir()
    
    if provider == 'gmail':
        has_secrets = os.path.exists(config.get('gmail', {}).get('client_secrets_file', ''))
        has_token = os.path.exists(auth_dir / 'gmail_token.json')
        if not (has_secrets or has_token):
             logging.error(f"Gmail sync requires credentials. Please configure 'auth/credentials.json' or use the UI setup.")
             return

    if provider == 'm365':
        has_config = os.path.exists(config.get('m365', {}).get('client_config_file', ''))
        has_token = os.path.exists(auth_dir / 'm365_token.json')
        if not (has_config or has_token):
            logging.error(f"M365 sync requires credentials. Please configure 'auth/config.json' or use the UI setup.")
            return

    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    
    # Helper to check cancellation from UI
    def check_ui_cancellation():
        try:
            from email_archiver.server.app import sync_status
            return sync_status.get("is_cancelled", False)
        except:
            return False

    run_archiver_logic_internal(
        provider=provider,
        incremental=incremental,
        classify=classify,
        extract=extract,
        since=since,
        after_id=after_id,
        specific_id=specific_id,
        query=query,
        config=config,
        checkpoint=checkpoint,
        rename=rename,
        embed=embed,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        check_cancellation=check_ui_cancellation,
        local_only=local_only
    )

def run_archiver_logic_internal(
    provider,
    incremental=False,
    since=None,
    after_id=None,
    specific_id=None,
    query=None,
    classify=False,
    extract=False,
    openai_api_key=None,
    skip_promotional=False,
    metadata_output=None,
    llm_base_url=None,
    llm_api_key=None,
    llm_model=None,
    llm_timeout=None,
    webhook_url=None,
    webhook_secret=None,
    download_dir=None,
    config=None,
    checkpoint=None,
    db_path=None,
    local_only=False,
    check_cancellation=None,
    rename=False,
    embed=False
):
    # Handle specific ID override
    if specific_id:
        logging.info(f"Targeting specific email ID: {specific_id}")
        # Disable other filters to ensure we get exactly this email
        since = None
        after_id = None
        incremental = False
        query = None

    # Default 'since' to today if not provided to avoid downloading everything
    if not since and not after_id and not query and not specific_id and not local_only:
        since = datetime.now().strftime('%Y-%m-%d')
        logging.info(f"No date filter provided. Defaulting to sync from: {since}")

    # Initialize DB
    db = DBHandler(db_path) if db_path else DBHandler()
    
    # Auto-Migrate legacy checkpoints if DB ones are missing
    migrate_checkpoints_to_db(CHECKPOINT_PATH, db)

    # Ensure download directory exists
    target_download_dir = download_dir if download_dir else config.get('app', {}).get('download_dir')
    if not target_download_dir:
        target_download_dir = get_download_dir()
    
    target_download_dir = str(resolve_path(target_download_dir))
    os.makedirs(target_download_dir, exist_ok=True)
    logging.info(f"Target download directory: {target_download_dir}")
    
    # Apply CLI webhook overrides
    webhook_config = config.get('webhook', {})
    if webhook_url:
        webhook_config['enabled'] = True
        webhook_config['url'] = webhook_url
    
    if webhook_secret:
        if 'headers' not in webhook_config:
            webhook_config['headers'] = {}
        webhook_config['headers']['Authorization'] = webhook_secret

    # Apply classification overrides
    classification_config = config.get('classification', {})
    if classify:
        classification_config['enabled'] = True
    
    if openai_api_key:
        classification_config['openai_api_key'] = openai_api_key
    
    if llm_api_key:
        classification_config['api_key'] = llm_api_key
        
    if llm_model:
        classification_config['model'] = llm_model
    
    if skip_promotional and classify:
        if 'skip_categories' not in classification_config:
            classification_config['skip_categories'] = []
        if 'promotional' not in classification_config['skip_categories']:
            classification_config['skip_categories'].append('promotional')
    
    if metadata_output:
        classification_config['metadata_file'] = metadata_output
    
    if llm_base_url:
        classification_config['base_url'] = llm_base_url
    
    # Initialize classifier
    config['classification'] = classification_config
    classifier = EmailClassifier(config)

    # Apply custom timeout if specified
    if llm_timeout and classifier.enabled:
        classifier.client = openai.OpenAI(
            api_key=classifier.client.api_key,
            base_url=classifier.base_url,
            timeout=llm_timeout
        )
        logging.info(f"Using custom LLM timeout: {llm_timeout}s")

    # Apply extraction overrides
    extraction_config = config.get('extraction', {})
    if extract:
        extraction_config['enabled'] = True
    config['extraction'] = extraction_config

    # Initialize extractor
    extractor = EmailExtractor(config)

    # Apply custom timeout to extractor if specified
    if llm_timeout and extractor.enabled:
        extractor.client = openai.OpenAI(
            api_key=extractor.client.api_key,
            base_url=extractor.base_url,
            timeout=llm_timeout
        )

    # Perform health checks if LLM features are enabled
    if not local_only:
        if classifier.enabled:
            classifier.check_health()
        if extractor.enabled:
            extractor.check_health()

    # Open metadata file with try-finally to ensure proper cleanup
    metadata_file_handle = None

    # Initialize checkpoint variables early to avoid UnboundLocalError in finally block
    current_gmail_checkpoint = db.get_checkpoint('gmail') or checkpoint.get('gmail', {}).get('last_internal_date', 0)
    current_m365_checkpoint = db.get_checkpoint('m365') or checkpoint.get('m365', {}).get('last_received_time', "1970-01-01T00:00:00Z")

    try:
        if classifier.enabled or extractor.enabled:
            metadata_path = classification_config.get('metadata_file', 'email_metadata.jsonl')
            metadata_file_handle = open(metadata_path, 'a', encoding='utf-8')
            logging.info(f"Metadata will be saved to: {metadata_path}")

        handler = None
        if provider == 'gmail':
            handler = GmailHandler(config)
        elif provider == 'm365':
            handler = GraphHandler(config)

        logging.info(f"Initialized {provider} handler.")


        # ---------------------------
        # Local File Mapping (for efficiency)
        # ---------------------------
        local_file_map = {} # short_id -> full_path
        for f in os.listdir(target_download_dir):
            if f.endswith('.eml'):
                # Filename format: ..._[ID].eml
                parts = f.split('_')
                if len(parts) >= 1:
                    short_id = parts[-1].replace('.eml', '')
                    local_file_map[short_id] = os.path.join(target_download_dir, f)

        if local_only:
            logging.info("Local-only mode: Building processing list from disk...")
            ids_to_fetch = []
            for short_id, path in local_file_map.items():
                # We don't have the full ID, but we can use the short one as a placeholder
                # if it's not in the DB.
                ids_to_fetch.append({'id': short_id, 'local_path': path})
        else:
            # ---------------------------
            # Query Construction Logic
            # ---------------------------
            ids_to_fetch = []

            if provider == 'gmail':
                query_parts = []

                if specific_id:
                    # Specific ID overrides everything else
                    # Distinguish between Message-ID headers (contain "@") and Gmail internal IDs
                    if "@" in specific_id:
                        # This is a Message-ID header (RFC 2822), use rfc822msgid: operator
                        query_parts.append(f"rfc822msgid:{specific_id}")
                    else:
                        # This is a Gmail internal ID, skip search and fetch directly
                        ids_to_fetch = [{'id': specific_id}]
                        logging.info(f"Gmail Direct ID: {specific_id}")
                else:
                    if query:
                        query_parts.append(query)
                        
                    if since:
                        # Gmail uses YYYY/MM/DD
                        date_str = since.replace('-', '/')
                        query_parts.append(f"after:{date_str}")
                        
                    if incremental:
                        # Checkpoint for Gmail: 'last_internal_date' (milliseconds)
                        last_ts = db.get_checkpoint('gmail')
                        if not last_ts:
                             # Fallback to legay if needed (migration should have handled it)
                             last_ts = checkpoint.get('gmail', {}).get('last_internal_date', 0)
                        
                        if last_ts:
                            # internalDate is ms, divide by 1000
                            ts_seconds = int(int(last_ts) / 1000)
                            query_parts.append(f"after:{ts_seconds}")
                    
                    # 'after-id' logic for Gmail is tricky without specific API calls to get that ID's date first.
                    # Implemented simply by warning or assuming user might provide custom query.
                    if after_id:
                        logging.warning("--after-id not fully implemented for Gmail automatic date resolution. Use --query for precise control.")

                # Only fetch if we haven't already set ids_to_fetch directly (e.g., for Gmail internal IDs)
                if not ids_to_fetch:
                    final_query = " ".join(query_parts)
                    logging.info(f"Gmail Query: {final_query}")

                    # Fetch IDs (returns dicts with 'id', 'threadId')
                    messages = handler.fetch_ids(final_query)
                    ids_to_fetch = messages
    
            elif provider == 'm365':
                if specific_id:
                     # Direct ID targeting for M365 (bypass filter query)
                     ids_to_fetch = [{'id': specific_id}]
                     logging.info(f"M365 Direct ID: {specific_id}")
                else:
                    filter_parts = []
                    # Since
                    if since:
                        filter_parts.append(f"receivedDateTime ge {since}T00:00:00Z")
                        
                    # Incremental
                    if incremental:
                        last_time = db.get_checkpoint('m365')
                        if not last_time:
                            last_time = checkpoint.get('m365', {}).get('last_received_time', "1970-01-01T00:00:00Z")
                        filter_parts.append(f"receivedDateTime gt {last_time}")
                        
                    # After-ID (Resolve ID to time first would be ideal, but for now just support custom query or since)
                    if after_id: 
                        # Implementation for resolving ID would go here, skipping for MVP/Simplicity unless requested
                         logging.warning("--after-id logic requires extra roundtrip, skipping specific resolution for now.")
        
                    final_filter = " and ".join(filter_parts) if filter_parts else None
                    
                    logging.info(f"M365 Filter: {final_filter}")
                    logging.info(f"M365 Search: {query}")
                    
                    # Fetch IDs (returns dicts with 'id', 'receivedDateTime')
                    messages = handler.fetch_ids(filter_str=final_filter, search_str=query)
                    ids_to_fetch = messages
            
        logging.info(f"Starting download for {len(ids_to_fetch)} messages...")
        
        # ---------------------------
        # Download Loop
        # ---------------------------
        success_count = 0
        max_checkpoint_val = 0 # Track strict ordering if possible, or just max seen

        for i, msg in enumerate(tqdm(ids_to_fetch)):
            # Check for cancellation
            if check_cancellation and check_cancellation():
                logging.info("Sync cancelled by user. Stopping loop...")
                break
                
            msg_id = msg['id']
    
            file_content = None
            metadata = {} # Initialize as dict to avoid NoneType errors
            
            # EFFICIENCY: Check if we have it on disk already
            local_path = msg.get('local_path')
            if not local_path:
                short_id = msg_id[-8:] if len(msg_id) > 8 else msg_id
                if short_id in local_file_map:
                    local_path = local_file_map[short_id]
            
            if local_path:
                logging.info(f"Using local file for {msg_id}: {os.path.basename(local_path)}")
                try:
                    with open(local_path, 'rb') as f:
                        file_content = f.read()
                    # We still need to determine the 'provider internal date' for checkpointing
                    # If it's M365, we might have it in the msg dict from fetch_ids
                    if provider == 'm365':
                        metadata = msg
                    # If Gmail, we'll try to parse it from the EML or just use the file date as fallback
                except Exception as e:
                    logging.error(f"Failed to read local file {local_path}: {e}")
    
            if not file_content:
                if local_only:
                    continue # Skip if not on disk and in local-only mode
                    
                if provider == 'gmail':
                    file_content, internal_date = handler.download_message(msg_id)
                    metadata = {'internalDate': internal_date}
                elif provider == 'm365':
                    file_content = handler.download_message(msg_id)
                    metadata = msg
            
            if file_content:
                from email import message_from_bytes
                from email_archiver.core.utils import decode_mime_header
                email_obj = message_from_bytes(file_content)
                subject = decode_mime_header(email_obj.get('subject', 'No Subject'))
                sender = decode_mime_header(email_obj.get('from', 'Unknown'))
                recipients_to = decode_mime_header(email_obj.get('to', ''))
                recipients_cc = decode_mime_header(email_obj.get('cc', ''))
                recipients_bcc = decode_mime_header(email_obj.get('bcc', ''))
                
                classification = None
                should_skip = False
                
                if classifier.enabled:
                    classification = classifier.classify_email(email_obj, subject, sender, recipients_to, recipients_cc)
                    if classification:
                        should_skip = classifier.should_skip(classification)
                        if should_skip:
                            logging.info(f"Skipping email '{subject[:50]}...' (category: {classification.get('category')})")
                            continue
                
                extraction = None
                if extractor.enabled:
                    extraction = extractor.extract_metadata(email_obj, subject, sender)

                # Determine AI processing status for database tracking
                ai_classification_status = None
                ai_extraction_status = None
                ai_processing_error = None

                # Classification status
                if classifier.enabled or classifier.error_handler.stats['total_calls'] > 0:
                    if classification:
                        ai_classification_status = 'success'
                    elif classifier.error_handler.is_circuit_open():
                        ai_classification_status = 'disabled'
                        ai_processing_error = classifier.error_handler.circuit_breaker.get('open_reason', 'Unknown error')
                    else:
                        ai_classification_status = 'failed'
                        # Get last error from error handler if available
                        if classifier.error_handler.stats['errors_by_type']:
                            error_types = list(classifier.error_handler.stats['errors_by_type'].keys())
                            ai_processing_error = f"Classification failed: {', '.join(error_types)}"

                # Extraction status
                if extractor.enabled or extractor.error_handler.stats['total_calls'] > 0:
                    if extraction:
                        ai_extraction_status = 'success'
                    elif extractor.error_handler.is_circuit_open():
                        ai_extraction_status = 'disabled'
                        if not ai_processing_error:  # Don't overwrite classification error
                            ai_processing_error = extractor.error_handler.circuit_breaker.get('open_reason', 'Unknown error')
                    else:
                        ai_extraction_status = 'failed'
                        if not ai_processing_error and extractor.error_handler.stats['errors_by_type']:
                            error_types = list(extractor.error_handler.stats['errors_by_type'].keys())
                            ai_processing_error = f"Extraction failed: {', '.join(error_types)}"

                timestamp = datetime.now()
                
                if provider == 'm365' and metadata.get('receivedDateTime'):
                    timestamp = metadata['receivedDateTime']
                    if timestamp > current_m365_checkpoint:
                        current_m365_checkpoint = timestamp
                        
                elif provider == 'gmail' and metadata.get('internalDate'):
                    ts_ms = int(metadata['internalDate'])
                    timestamp = datetime.fromtimestamp(ts_ms / 1000.0)
                    if ts_ms > int(current_gmail_checkpoint):
                        current_gmail_checkpoint = ts_ms
                
                # Fallback for local indexing where metadata might be empty
                if timestamp == datetime.now() and email_obj.get('date'):
                    from email.utils import parsedate_to_datetime
                    try:
                        timestamp = parsedate_to_datetime(email_obj.get('date'))
                    except:
                        pass
                
                if embed and (classification or extraction):
                    logging.info(f"Embedding AI metadata into headers for {msg['id']}")
                    email_obj = embed_metadata_in_message(email_obj, metadata, classification, extraction)
                    file_content = email_obj.as_bytes()
                
                if local_only and local_path:
                    file_path = local_path
                else:
                    filename = generate_filename(subject, timestamp, internal_id=msg['id'], use_slug=rename)
                    file_path = os.path.join(target_download_dir, filename)
                
                # Check if we should skip writing based on presence AND lack of AI request
                if os.path.exists(file_path) and not (classifier.enabled or extractor.enabled or embed):
                    logging.info(f"Skipping {filename}, already exists and no re-analysis requested.")
                    # Auto-Index: If record exists but path changed, update it.
                    # If record doesn't exist, create it.
                    if db.get_email(msg['id']):
                        db.update_email_path(msg['id'], file_path)
                    else:
                        db.record_email(
                            message_id=msg['id'],
                            provider=provider,
                            subject=subject,
                            sender=sender,
                            recipients=f"{recipients_to}, {recipients_cc}".strip(", "),
                            received_at=timestamp,
                            file_path=file_path,
                            classification=classification,
                            extraction=extraction,
                            ai_classification_status=ai_classification_status,
                            ai_extraction_status=ai_extraction_status,
                            ai_processing_error=ai_processing_error
                        )
                else:
                    with open(file_path, 'wb') as f:
                        f.write(file_content)
                    success_count += 1
                    
                    if (classifier.enabled or extractor.enabled) and metadata_file_handle:
                        metadata_entry = {
                            "message_id": msg['id'],
                            "subject": subject,
                            "from": sender,
                            "to": recipients_to,
                            "cc": recipients_cc,
                            "bcc": recipients_bcc,
                            "date": timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
                            "classification": classification,
                            "extraction": extraction,
                            "file_path": file_path
                        }
                        try:
                            metadata_file_handle.write(json.dumps(metadata_entry) + '\n')
                            metadata_file_handle.flush()
                        except Exception as e:
                            logging.error(f"Failed to write metadata: {e}")
                    
                    webhook_config = config.get('webhook', {})
                    if webhook_config.get('enabled'):
                        send_to_webhook(
                            file_path, 
                            webhook_config.get('url'), 
                            headers=webhook_config.get('headers')
                        )
                    
                    # Record in Database
                    db.record_email(
                        message_id=msg['id'],
                        provider=provider,
                        subject=subject,
                        sender=sender,
                        recipients=f"{recipients_to}, {recipients_cc}".strip(", "),
                        received_at=timestamp,
                        file_path=file_path,
                        classification=classification,
                        extraction=extraction,
                        ai_classification_status=ai_classification_status,
                        ai_extraction_status=ai_extraction_status,
                        ai_processing_error=ai_processing_error
                    )
                    
                if success_count % 10 == 0 and success_count > 0:
                    if provider == 'm365':
                        db.save_checkpoint('m365', current_m365_checkpoint)
                    elif provider == 'gmail':
                        db.save_checkpoint('gmail', current_gmail_checkpoint)


    finally:
        # ALWAYS close file handle, even if there's an exception
        if metadata_file_handle:
            try:
                metadata_file_handle.flush()  # Ensure data is written
                metadata_file_handle.close()
                logging.debug("Metadata file closed successfully")
            except Exception as e:
                logging.error(f"Error closing metadata file: {e}")

        # Save final checkpoints
        if provider == 'm365':
            db.save_checkpoint('m365', current_m365_checkpoint)
        elif provider == 'gmail':
            db.save_checkpoint('gmail', current_gmail_checkpoint)

    logging.info(f"Sync complete. Processed {len(ids_to_fetch)} messages. New files: {success_count}. Updated: {len(ids_to_fetch) - success_count if local_only else 'N/A'}")

    # Report AI processing statistics
    if classifier.enabled or classifier.error_handler.stats['total_calls'] > 0:
        classifier_stats = classifier.format_stats()
        if classifier_stats:
            logging.info(f"Classification: {classifier_stats}")

    if extractor.enabled or extractor.error_handler.stats['total_calls'] > 0:
        extractor_stats = extractor.format_stats()
        if extractor_stats:
            logging.info(f"Extraction: {extractor_stats}")

if __name__ == '__main__':
    main()
