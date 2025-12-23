import argparse
import yaml
import json
import os
import logging
from datetime import datetime
from tqdm import tqdm

from email_archiver.core.utils import setup_logging, generate_filename, send_to_webhook
from email_archiver.core.gmail_handler import GmailHandler
from email_archiver.core.graph_handler import GraphHandler
from email_archiver.core.classifier import EmailClassifier
from email_archiver.core.extractor import EmailExtractor

CONFIG_PATH = 'config/settings.yaml'
CHECKPOINT_PATH = 'config/checkpoint.json'

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_checkpoint(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_checkpoint(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Email-to-EML Secure Archiver")
    parser.add_argument('--provider', choices=['gmail', 'm365'], required=True, help='Email provider')
    parser.add_argument('--since', help='Download emails since date (YYYY-MM-DD)')
    parser.add_argument('--after-id', help='Download emails received after a specific unique Message ID')
    parser.add_argument('--incremental', action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--query', help='Custom advanced query string')
    # Webhook CLI overrides
    parser.add_argument('--webhook-url', help='Webhook URL to send .eml files to')
    parser.add_argument('--webhook-secret', help='Authorization secret for the webhook (sets Authorization header)')
    # Download directory override
    parser.add_argument('--download-dir', help='Directory to save downloaded .eml files (default: downloads/)')
    # Classification arguments
    parser.add_argument('--classify', action='store_true', help='Enable AI-powered email classification')
    parser.add_argument('--openai-api-key', help='OpenAI API key for classification')
    parser.add_argument('--skip-promotional', action='store_true', help='Skip promotional emails (requires --classify)')
    parser.add_argument('--metadata-output', help='Output file for classification metadata (JSONL format)')
    parser.add_argument('--llm-provider', choices=['openai', 'ollama', 'lm_studio', 'local'], default='openai', help='LLM provider for classification (default: openai)')
    parser.add_argument('--llm-base-url', help='Custom base URL for local LLM API (e.g., http://localhost:11434/v1)')
    parser.add_argument('--extract', action='store_true', help='Enable advanced metadata extraction (v0.5.0)')
    parser.add_argument('--ui', action='store_true', help='Start the web-based dashboard and UI (v0.6.0)')
    
    args = parser.parse_args()
    
    # Handle UI early
    if args.ui:
        try:
            from email_archiver.server.app import start_server
            start_server()
            return
        except ImportError:
            logging.error("UI dependencies not found. Install with: pip install 'email-archiver[ui]'")
            return

    if not args.provider:
        parser.error("--provider is required unless using --ui")
    
    config = load_config(CONFIG_PATH)
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    
    # Ensure download directory exists (use CLI arg if provided, otherwise config)
    download_dir = args.download_dir if args.download_dir else config.get('app', {}).get('download_dir', 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    
    # Apply CLI webhook overrides
    webhook_config = config.get('webhook', {})
    if args.webhook_url:
        webhook_config['enabled'] = True
        webhook_config['url'] = args.webhook_url
    
    if args.webhook_secret:
        if 'headers' not in webhook_config:
            webhook_config['headers'] = {}
        # Assuming simple bearer or raw match, relying on user or generic header usage
        # Usually webhooks use a specific header, but standard is often Authorization
        webhook_config['headers']['Authorization'] = args.webhook_secret

    # Apply CLI classification overrides
    classification_config = config.get('classification', {})
    if args.classify:
        classification_config['enabled'] = True
    
    if args.openai_api_key:
        classification_config['openai_api_key'] = args.openai_api_key
    
    if args.skip_promotional and args.classify:
        if 'promotional' not in classification_config.get('skip_categories', []):
            if 'skip_categories' not in classification_config:
                classification_config['skip_categories'] = []
            classification_config['skip_categories'].append('promotional')
    
    if args.metadata_output:
        classification_config['metadata_file'] = args.metadata_output
    
    if args.llm_provider:
        classification_config['provider'] = args.llm_provider
        
    if args.llm_base_url:
        classification_config['base_url'] = args.llm_base_url
    
    # Initialize classifier
    config['classification'] = classification_config
    classifier = EmailClassifier(config)
    
    # Apply CLI extraction overrides
    extraction_config = config.get('extraction', {})
    if args.extract:
        extraction_config['enabled'] = True
    config['extraction'] = extraction_config
    
    # Initialize extractor
    extractor = EmailExtractor(config)
    
    # Open metadata file if classification OR extraction is enabled
    metadata_file_handle = None
    if classifier.enabled or extractor.enabled:
        metadata_path = classification_config.get('metadata_file', 'email_metadata.jsonl')
        metadata_file_handle = open(metadata_path, 'a', encoding='utf-8')
        logging.info(f"Metadata will be saved to: {metadata_path}")

    handler = None
    if args.provider == 'gmail':
        handler = GmailHandler(config)
    elif args.provider == 'm365':
        handler = GraphHandler(config)
        
    logging.info(f"Initialized {args.provider} handler.")
    
    # ---------------------------
    # Query Construction Logic
    # ---------------------------
    ids_to_fetch = []
    
    if args.provider == 'gmail':
        query_parts = []
        if args.query:
            query_parts.append(args.query)
            
        if args.since:
            # Gmail uses YYYY/MM/DD
            date_str = args.since.replace('-', '/')
            query_parts.append(f"after:{date_str}")
            
        if args.incremental:
            # Checkpoint for Gmail: 'last_internal_date' (milliseconds)
            last_ts = checkpoint.get('gmail', {}).get('last_internal_date', 0)
            # Convert ms to seconds for query logic if needed, but Gmail filter API is day-based or ID based (?)
            # Actually, `after:` takes a date or a timestamp in seconds
            if last_ts:
                # internalDate is ms, divide by 1000
                ts_seconds = int(int(last_ts) / 1000)
                query_parts.append(f"after:{ts_seconds}")
        
        # 'after-id' logic for Gmail is tricky without specific API calls to get that ID's date first.
        # Implemented simply by warning or assuming user might provide custom query.
        if args.after_id:
            logging.warning("--after-id not fully implemented for Gmail automatic date resolution. Use --query for precise control.")
        
        final_query = " ".join(query_parts)
        logging.info(f"Gmail Query: {final_query}")
        
        # Fetch IDs (returns dicts with 'id', 'threadId')
        messages = handler.fetch_ids(final_query)
        # Sort by internalDate if possible? The list API doesn't return internalDate by default, only IDs.
        # We might need to fetch details or just download all. 
        # But for checkpointing, we want to know the max internalDate. 
        # For now, we put them in a list.
        ids_to_fetch = messages

    elif args.provider == 'm365':
        filter_parts = []
        # Since
        if args.since:
            filter_parts.append(f"receivedDateTime ge {args.since}T00:00:00Z")
            
        # Incremental
        if args.incremental:
            last_time = checkpoint.get('m365', {}).get('last_received_time', "1970-01-01T00:00:00Z")
            filter_parts.append(f"receivedDateTime gt {last_time}")
            
        # After-ID (Resolve ID to time first would be ideal, but for now just support custom query or since)
        if args.after_id: 
            # Implementation for resolving ID would go here, skipping for MVP/Simplicity unless requested
             logging.warning("--after-id logic requires extra roundtrip, skipping specific resolution for now.")

        final_filter = " and ".join(filter_parts) if filter_parts else None
        
        logging.info(f"M365 Filter: {final_filter}")
        logging.info(f"M365 Search: {args.query}")
        
        # Fetch IDs (returns dicts with 'id', 'receivedDateTime')
        messages = handler.fetch_ids(filter_str=final_filter, search_str=args.query)
        ids_to_fetch = messages
        
    logging.info(f"Starting download for {len(ids_to_fetch)} messages...")
    
    # ---------------------------
    # Download Loop
    # ---------------------------
    success_count = 0
    max_checkpoint_val = 0 # Track strict ordering if possible, or just max seen
    
    # For checkpoint updates
    current_gmail_checkpoint = checkpoint.get('gmail', {}).get('last_internal_date', 0)
    current_m365_checkpoint = checkpoint.get('m365', {}).get('last_received_time', "1970-01-01T00:00:00Z")

    for i, msg in enumerate(tqdm(ids_to_fetch)):
        file_content = None
        metadata = None
        
        if args.provider == 'gmail':
            file_content, internal_date = handler.download_message(msg['id'])
            metadata = {'internalDate': internal_date}
        elif args.provider == 'm365':
            file_content = handler.download_message(msg['id'])
            # M365 fetch included receivedDateTime in the list object 'msg'
            metadata = msg
        
        if file_content:
            # We need some metadata for the filename.
            from email import message_from_bytes
            email_obj = message_from_bytes(file_content)
            subject = email_obj.get('subject', 'No Subject')
            sender = email_obj.get('from', 'Unknown')
            recipients_to = email_obj.get('to', '')
            recipients_cc = email_obj.get('cc', '')
            recipients_bcc = email_obj.get('bcc', '')
            
            # Classify email if enabled
            classification = None
            should_skip = False
            
            if classifier.enabled:
                classification = classifier.classify_email(email_obj, subject, sender, recipients_to, recipients_cc)
                if classification:
                    should_skip = classifier.should_skip(classification)
                    
                    if should_skip:
                        logging.info(f"Skipping email '{subject[:50]}...' (category: {classification.get('category')})")
                        continue
            
            # Extract advanced metadata if enabled
            extraction = None
            if extractor.enabled:
                extraction = extractor.extract_metadata(email_obj, subject, sender)
            
            timestamp = datetime.now()
            
            if args.provider == 'm365' and 'receivedDateTime' in metadata:
                timestamp = metadata['receivedDateTime'] # String ISO
                if timestamp > current_m365_checkpoint:
                    current_m365_checkpoint = timestamp
                    
            elif args.provider == 'gmail' and 'internalDate' in metadata and metadata['internalDate']:
                # Gmail internalDate is MS string
                ts_ms = int(metadata['internalDate'])
                timestamp = datetime.fromtimestamp(ts_ms / 1000.0)
                
                if ts_ms > int(current_gmail_checkpoint):
                    current_gmail_checkpoint = ts_ms
            
            filename = generate_filename(subject, timestamp, internal_id=msg['id'])
            file_path = os.path.join(download_dir, filename)
            
            # Check existence
            if os.path.exists(file_path):
                logging.info(f"Skipping {filename}, already exists.")
            else:
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                success_count += 1
                
                # Save classification/extraction metadata
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
                    metadata_file_handle.write(json.dumps(metadata_entry) + '\n')
                    metadata_file_handle.flush()
                
                # Webhook integration
                webhook_config = config.get('webhook', {})
                if webhook_config.get('enabled'):
                    send_to_webhook(
                        file_path, 
                        webhook_config.get('url'), 
                        headers=webhook_config.get('headers')
                    )
                
            # Checkpoint save every 10
            if success_count % 10 == 0 and success_count > 0:
                if args.provider == 'm365':
                    checkpoint['m365']['last_received_time'] = current_m365_checkpoint
                elif args.provider == 'gmail':
                    checkpoint['gmail']['last_internal_date'] = current_gmail_checkpoint
                save_checkpoint(CHECKPOINT_PATH, checkpoint)
        
    # Close metadata file
    if metadata_file_handle:
        metadata_file_handle.close()
    
    # Final Checkpoint Save
    if args.provider == 'm365':
        checkpoint['m365']['last_received_time'] = current_m365_checkpoint
    elif args.provider == 'gmail':
        checkpoint['gmail']['last_internal_date'] = current_gmail_checkpoint
    
    save_checkpoint(CHECKPOINT_PATH, checkpoint)
        
    # Final Checkpoint Save
    if args.provider == 'm365':
        checkpoint['m365']['last_received_time'] = current_m365_checkpoint
        save_checkpoint(CHECKPOINT_PATH, checkpoint)
        
    logging.info(f"Download complete. Processed {len(ids_to_fetch)} messages, Downloaded {success_count} new files.")

if __name__ == '__main__':
    main()
