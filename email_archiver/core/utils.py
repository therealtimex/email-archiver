import re
import logging
import os
import sys
from datetime import datetime

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

def generate_filename(subject, timestamp, internal_id=None):
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
    safe_subject = sanitize_filename(subject)
    
    # If ID is provided, append a short hash or the ID itself if safe
    # Using last 8 chars of ID if it's long, or full if short
    id_suffix = f"_{internal_id[-8:]}" if internal_id else ""
    
    return f"{date_str}_{safe_subject}{id_suffix}.eml"

def send_to_webhook(file_path, url, headers=None):
    """
    Sends the file to the specified webhook URL.
    """
    import requests # Import here to avoid circular dependencies if any, or just convenience
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'message/rfc822')}
            response = requests.post(url, files=files, headers=headers)
            response.raise_for_status()
        logging.info(f"Successfully sent {os.path.basename(file_path)} to webhook.")
    except Exception as e:
        logging.error(f"Failed to send {file_path} to webhook: {e}")
