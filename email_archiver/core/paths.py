import os
from pathlib import Path
import logging

# Allowed base directories
USER_HOME = Path.home()
ALLOWED_BASE_DIRS = [
    USER_HOME / ".email-archiver",  # Default
    Path("/tmp/email-archiver"),    # Temp
    USER_HOME / "Documents" / "email-archiver",
    USER_HOME / "Library" / "Application Support" / "EESA",  # macOS
    USER_HOME / ".local" / "share" / "email-archiver",  # Linux
]

def is_safe_path(path: Path) -> bool:
    """Check if path is safe to use"""
    try:
        abs_path = path.resolve()

        # Check if in explicitly allowed directory
        for allowed in ALLOWED_BASE_DIRS:
            try:
                abs_path.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue

        # Allow anywhere under user's home (but not system dirs)
        try:
            abs_path.relative_to(USER_HOME)

            # Block sensitive subdirectories
            path_str = str(abs_path).lower()
            blocked = ['/system/', '/library/apple', '/usr/', '/bin/', '/sbin/', '/etc/']
            if any(block in path_str for block in blocked):
                logging.error(f"⚠️ Path blocked (system directory): {abs_path}")
                return False

            return True

        except ValueError:
            pass

        logging.error(f"⚠️ Path outside allowed locations: {abs_path}")
        return False

    except Exception as e:
        logging.error(f"Path validation error: {e}")
        return False

def get_data_dir() -> Path:
    """Returns the base data directory, defaults to ~/.email-archiver."""
    env_dir = os.getenv("EESA_DATA_DIR")

    if env_dir:
        requested_path = Path(env_dir).absolute()

        if not is_safe_path(requested_path):
            logging.error(
                f"❌ EESA_DATA_DIR points to unsafe location: {requested_path}\n"
                f"   Allowed locations:\n"
                f"   - Anywhere under {USER_HOME}\n"
                f"   - Excluding system directories (/System, /usr, /bin, etc.)\n"
                f"   Falling back to default: {USER_HOME / '.email-archiver'}"
            )
            return (USER_HOME / ".email-archiver").absolute()

        return requested_path

    return (USER_HOME / ".email-archiver").absolute()

def get_config_path() -> Path:
    """Returns the path to settings.yaml."""
    env_path = os.getenv("EESA_CONFIG_PATH")
    if env_path:
        path = Path(env_path).absolute()
        if is_safe_path(path):
            return path
        logging.warning(f"EESA_CONFIG_PATH unsafe, using default")
    return get_data_dir() / "config" / "settings.yaml"

def get_db_path() -> Path:
    """Returns the SQLite database path."""
    env_path = os.getenv("EESA_DB_PATH")
    if env_path:
        path = Path(env_path).absolute()
        if is_safe_path(path):
            return path
        logging.warning(f"EESA_DB_PATH unsafe, using default")
    return get_data_dir() / "email_archiver.sqlite"

def get_log_path() -> Path:
    """Returns the log file path."""
    env_path = os.getenv("EESA_LOG_FILE")
    if env_path:
        # Special case: stdout/stderr are allowed
        if env_path.lower() in ['stdout', 'stderr']:
            return Path(env_path)
        path = Path(env_path).absolute()
        if is_safe_path(path):
            return path
        logging.warning(f"EESA_LOG_FILE unsafe, using default")
    return get_data_dir() / "sync.log"

def get_auth_dir() -> Path:
    """Returns the directory for OAuth tokens and credentials."""
    env_path = os.getenv("EESA_AUTH_DIR")
    if env_path:
        path = Path(env_path).absolute()
        if is_safe_path(path):
            return path
        logging.warning(f"EESA_AUTH_DIR unsafe, using default")
    
    # Check local directory first for developer convenience
    local_auth = Path.cwd() / "auth"
    if local_auth.exists() and local_auth.is_dir() and is_safe_path(local_auth):
        return local_auth
        
    return get_data_dir() / "auth"

def get_download_dir() -> Path:
    """Returns the default download directory."""
    env_path = os.getenv("EESA_DOWNLOAD_DIR")
    if env_path:
        path = Path(env_path).absolute()
        if is_safe_path(path):
            return path
        logging.warning(f"EESA_DOWNLOAD_DIR unsafe, using default")
    return get_data_dir() / "downloads"

def resolve_path(path_str: str) -> Path:
    """Resolves a path string relative to the data directory if it's not absolute."""
    path = Path(path_str)
    if path.is_absolute():
        if is_safe_path(path):
            return path
        logging.warning(f"Absolute path unsafe: {path}, using relative to data dir")

    # Relative paths are safe (relative to data dir)
    return get_data_dir() / path

def get_llm_config() -> dict:
    """
    Returns a normalized LLM configuration from environment variables.
    Priority: LLM_* > OPENAI_* > Defaults
    """
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL") or "gpt-4o-mini"
    
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model
    }
