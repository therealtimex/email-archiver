import os
from pathlib import Path

def get_data_dir() -> Path:
    """Returns the base data directory, defaults to ~/.email-archiver."""
    env_dir = os.getenv("EESA_DATA_DIR")
    if env_dir:
        return Path(env_dir).absolute()
    return (Path.home() / ".email-archiver").absolute()

def get_config_path() -> Path:
    """Returns the path to settings.yaml."""
    env_path = os.getenv("EESA_CONFIG_PATH")
    if env_path:
        return Path(env_path).absolute()
    return get_data_dir() / "config" / "settings.yaml"

def get_db_path() -> Path:
    """Returns the SQLite database path."""
    env_path = os.getenv("EESA_DB_PATH")
    if env_path:
        return Path(env_path).absolute()
    return get_data_dir() / "email_archiver.sqlite"

def get_log_path() -> Path:
    """Returns the log file path."""
    env_path = os.getenv("EESA_LOG_FILE")
    if env_path:
        return Path(env_path).absolute()
    return get_data_dir() / "sync.log"

def get_auth_dir() -> Path:
    """Returns the directory for OAuth tokens and credentials."""
    env_path = os.getenv("EESA_AUTH_DIR")
    if env_path:
        return Path(env_path).absolute()
    return get_data_dir() / "auth"

def get_download_dir() -> Path:
    """Returns the default download directory."""
    env_path = os.getenv("EESA_DOWNLOAD_DIR")
    if env_path:
        return Path(env_path).absolute()
    return get_data_dir() / "downloads"

def resolve_path(path_str: str) -> Path:
    """Resolves a path string relative to the data directory if it's not absolute."""
    path = Path(path_str)
    if path.is_absolute():
        return path
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
