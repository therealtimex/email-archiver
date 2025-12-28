import re
import logging
import os
import sys
import json
import base64
from datetime import datetime
from email.utils import formatdate
from email.header import decode_header
import requests
import ipaddress
import socket
from urllib.parse import urlparse

def setup_logging(log_file=None):
    """
    Configures the logging system to write to a file and the console.
    If log_file is 'stdout' or 'stderr', it logs only to that stream.
    """
    from email_archiver.core.paths import get_log_path
    
    actual_log_path = log_file if log_file else str(get_log_path())
    
    handlers = []
    if actual_log_path.lower() == 'stdout':
        handlers.append(logging.StreamHandler(sys.stdout))
    elif actual_log_path.lower() == 'stderr':
        handlers.append(logging.StreamHandler(sys.stderr))
    else:
        # Standard file + console
        try:
            os.makedirs(os.path.dirname(os.path.abspath(actual_log_path)), exist_ok=True)
            handlers.append(logging.FileHandler(actual_log_path))
        except Exception as e:
            print(f"Warning: Could not create log file at {actual_log_path}: {e}")
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    logging.info(f"Logging initialized. Log target: {actual_log_path}")

def decode_mime_header(header_value):
    """
    Decodes MIME-encoded email headers (RFC 2047) to plain text.

    Handles headers like:
        =?UTF-8?B?W1RDVFQgxJHhuqV0IMSRYWldIEhvw6BuIHRoaeG7h24ga+G6v3QgcXXhuqMgaG/huqF0IA==?=
        =?UTF-8?B?xJHhu5luZyAyIHbDoCAz?=

    Returns:
        Decoded string in UTF-8
    """
    if not header_value:
        return header_value

    try:
        # decode_header returns a list of (decoded_bytes, charset) tuples
        decoded_parts = decode_header(header_value)

        # Reconstruct the string
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                # Decode bytes using the specified charset, or UTF-8 as fallback
                try:
                    result.append(part.decode(charset or 'utf-8'))
                except (UnicodeDecodeError, LookupError):
                    # If charset is invalid or decoding fails, try UTF-8
                    result.append(part.decode('utf-8', errors='replace'))
            else:
                # Already a string
                result.append(part)

        return ''.join(result)

    except Exception as e:
        logging.warning(f"Failed to decode MIME header: {e}. Returning raw value.")
        return header_value

def sanitize_filename(text):
    """
    Sanitizes a string to be safe for use as a filename.
    Removes characters: / \\ : * ? " < > |
    Truncates to a reasonable length to avoid OS limits.
    """
    if not text:
        return "No_Subject"
    
    # Replace illegal characters with underscore or nothing
    clean_text = re.sub(r'[\\/*?:"<>|]', '_', text)
    
    # Remove control characters
    clean_text = "".join(ch for ch in clean_text if ch.isprintable())
    
    # Collapse multiple underscores
    clean_text = re.sub(r'_{2,}', '_', clean_text)
    
    # Strip whitespace
    clean_text = clean_text.strip()
    
    # Truncate to 100 chars to leave room for date/id
    return clean_text[:100]

def slugify(text):
    """
    Converts a string to a safe, lowercase, hyphen-separated slug.
    Ideal for Linux/Cloud environments.
    """
    if not text:
        return "no-subject"
    
    # Convert to lowercase
    text = text.lower()
    
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    # Collapse multiple hyphens
    text = re.sub(r'-{2,}', '-', text)
    
    # Truncate to 100 chars
    return text[:100]

def generate_filename(subject, timestamp, internal_id=None, use_slug=False):
    """
    Generates a standardized filename: YYYYMMDD_HHMM_[Subject]_[ID].eml
    """
    if isinstance(timestamp, str):
        # Try to parse ISO format if it's a string, or handle custom formats
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            # Fallback or more complex parsing if needed
            dt = datetime.now() 
    elif isinstance(timestamp, datetime):
        dt = timestamp
    else:
        dt = datetime.now()
        
    date_str = dt.strftime('%Y%m%d_%H%M')
    
    if use_slug:
        safe_subject = slugify(subject)
        sep = "-"
    else:
        safe_subject = sanitize_filename(subject)
        sep = "_"
    
    # If ID is provided, append a short hash or the ID itself if safe
    # Using last 8 chars of ID if it's long, or full if short
    id_suffix = f"{sep}{internal_id[-8:]}" if internal_id else ""
    
    if use_slug:
        # For slugified, use yyyymmdd-hhmm-slug-id.eml
        date_str = dt.strftime('%Y%m%d-%H%M')
        return f"{date_str}-{safe_subject}{id_suffix}.eml"
    
    return f"{date_str}_{safe_subject}{id_suffix}.eml"

def embed_metadata_in_message(email_obj, metadata, classification=None, extraction=None):
    """
    Injects AI-generated metadata as X-EESA headers into the email message object.
    """
    # X-EESA-Category
    if classification and classification.get('category'):
        email_obj['X-EESA-Category'] = classification['category']
        
    # X-EESA-Summary
    if extraction and extraction.get('summary'):
        email_obj['X-EESA-Summary'] = extraction['summary']
    elif classification and classification.get('summary'):
        email_obj['X-EESA-Summary'] = classification['summary']
        
    # X-EESA-Sentiment
    if classification and classification.get('sentiment'):
        email_obj['X-EESA-Sentiment'] = classification['sentiment']
        
    # X-EESA-Entities
    entities = []
    if extraction:
        if extraction.get('organizations'):
            entities.extend(extraction['organizations'])
        if extraction.get('people'):
            entities.extend(extraction['people'])
    if entities:
        email_obj['X-EESA-Entities'] = ", ".join(entities[:10]) # Limit to 10 entities
        
    # X-EESA-ID
    if metadata and metadata.get('id'):
        email_obj['X-EESA-ID'] = metadata['id']
        
    # X-EESA-Processed-At
    email_obj['X-EESA-Processed-At'] = formatdate(localtime=True)
    
    # X-EESA-Raw-JSON (Base64 encoded to avoid MIME breakage)
    raw_data = {
        "classification": classification,
        "extraction": extraction,
        "internal_metadata": metadata
    }
    json_str = json.dumps(raw_data)
    encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    email_obj['X-EESA-Raw-JSON'] = encoded_json
    
    return email_obj

def validate_webhook_url(url: str) -> bool:
    """Prevents SSRF by blocking private/internal IPs"""
    try:
        parsed = urlparse(url)

        # Must be HTTP(S)
        if parsed.scheme not in ['http', 'https']:
            logging.error(f"Invalid webhook scheme: {parsed.scheme}")
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Resolve to IP and check if private
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)

            # Block private/loopback/link-local addresses
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                logging.error(f"⚠️ Webhook URL resolves to private IP: {ip}")
                logging.error(f"   This could attack your internal network!")
                logging.error(f"   Blocked for your safety: {url}")
                return False

        except socket.gaierror:
            logging.error(f"Could not resolve webhook hostname: {hostname}")
            return False

        return True

    except Exception as e:
        logging.error(f"Webhook URL validation failed: {e}")
        return False

def send_to_webhook(file_path, url, headers=None):
    """
    Sends the file to the specified webhook URL with security checks.
    """
    # Validate URL first
    if not validate_webhook_url(url):
        logging.error(f"❌ Refusing to send to unsafe webhook URL")
        return False

    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'message/rfc822')}
            response = requests.post(
                url,
                files=files,
                headers=headers,
                timeout=30,  # Prevent hanging
                allow_redirects=False  # Prevent redirect-based attacks
            )
            response.raise_for_status()

        logging.info(f"✅ Successfully sent {os.path.basename(file_path)} to webhook.")
        return True

    except requests.Timeout:
        logging.error(f"⏱️ Webhook request timed out (>30s): {url}")
        return False

    except requests.RequestException as e:
        logging.error(f"❌ Failed to send to webhook: {e}")
        return False


    except Exception as e:
        logging.error(f"❌ Unexpected error sending to webhook: {e}")
        return False

def perform_reset():
    """
    Wipes all data for a clean slate.
    Deletes DB, Logs, and Downloads.
    Preserves Authentication.
    """
    import shutil
    from email_archiver.core.paths import get_db_path, get_log_path, get_download_dir
    
    deleted_items = []
    
    # 1. Delete DB
    db_path = get_db_path()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            logging.info(f"✅ Deleted database: {db_path}")
            deleted_items.append("Database")
        except Exception as e:
            logging.error(f"❌ Failed to delete database: {e}")
    
    # 2. Delete Logs
    log_path = get_log_path()
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
            logging.info(f"✅ Deleted logs: {log_path}")
            deleted_items.append("Logs")
        except Exception as e:
            logging.error(f"❌ Failed to delete logs: {e}")
            
    # 3. Delete Downloads
    dl_dir = get_download_dir()
    if os.path.exists(dl_dir):
        try:
            shutil.rmtree(dl_dir)
            logging.info(f"✅ Deleted downloads: {dl_dir}")
            deleted_items.append("Downloads Directory")
        except Exception as e:
            logging.error(f"❌ Failed to delete downloads directory: {e}")
            
    return deleted_items
