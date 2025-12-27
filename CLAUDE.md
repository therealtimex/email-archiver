# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Email-to-EML Secure Archiver (EESA) is a Python CLI tool and web dashboard that retrieves emails from Gmail and Microsoft 365 via OAuth2 and saves them as RFC822-compliant `.eml` files. It includes AI-powered classification, extraction, webhook integration, and supports both cloud and local LLMs.

## Development Commands

### Installation and Setup

```bash
# Install with UV (recommended)
uv sync

# Install with pip
pip install -e ".[ui]"

# Run from source
uv run email-archiver --help
```

### Running the Application

```bash
# CLI mode
uv run email-archiver --provider gmail --incremental

# Web UI mode
uv run email-archiver --ui --port 8000

# With classification
uv run email-archiver --provider gmail --classify --llm-model gpt-4o-mini

# Local processing only (no API calls)
uv run email-archiver --local-only --ui
```

### Testing and Development

```bash
# Run the FastAPI server directly
cd email_archiver/server
uvicorn app:app --reload --port 8000

# Check for syntax errors
python -m py_compile email_archiver/**/*.py
```

## Architecture

### Core Components

The architecture follows a **handler-based pattern** where each email provider has its own handler class that abstracts authentication and API interactions:

1. **Provider Handlers** (`email_archiver/core/`)
   - `GmailHandler`: Manages Gmail API via OAuth2 (uses google-api-python-client)
   - `GraphHandler`: Manages Microsoft Graph API via MSAL device flow
   - Both handlers support browser-based OAuth flows and token refresh

2. **AI Processing Pipeline**
   - `EmailClassifier`: Uses OpenAI-compatible APIs to classify emails into categories (important, promotional, transactional, etc.)
   - `EmailExtractor`: Extracts structured metadata (summaries, action items, invoices, dates)
   - Both support local LLMs (Ollama, LM Studio) via custom `base_url`

3. **Persistence Layer**
   - `DBHandler`: SQLite database for email metadata and incremental checkpointing
   - Replaced legacy `checkpoint.json` with database-backed state management
   - Migration logic exists in `main.py:migrate_checkpoints_to_db()`

4. **Web Dashboard** (`email_archiver/server/`)
   - FastAPI application serving HTML/JS frontend
   - Real-time sync status via polling endpoints
   - OAuth flow handled through `/auth/` endpoints
   - Templates in `server/templates/`, static assets in `server/static/`

### Configuration System

The application uses a **dual-layer configuration approach**:

1. **File-based config** (`config/settings.yaml`): Provider credentials, default behavior
2. **Environment variables**: Override defaults, especially for sandboxed environments

Key environment variables (defined in `core/paths.py`):
- `EESA_DATA_DIR`: Base directory for all data (default: `~/.email-archiver`)
- `EESA_CONFIG_PATH`: Path to settings.yaml
- `EESA_DB_PATH`: SQLite database location
- `EESA_AUTH_DIR`: OAuth token storage
- `EESA_DOWNLOAD_DIR`: Default .eml download location
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`: LLM configuration

### Authentication Flow

- **Gmail**: OAuth2 Authorization Code flow with refresh tokens
  - Tokens stored in `auth/gmail_token.json` (chmod 600)
  - Web UI uses `/api/gmail/auth-url` and `/api/gmail/auth-callback`

- **Microsoft 365**: MSAL Device Code flow
  - Token cache stored in `auth/m365_token.json`
  - Web UI uses `/api/m365/device-flow/initiate` and `/complete` endpoints

### Data Flow

1. User initiates sync via CLI or Web UI
2. Main orchestrator (`main.py:main()`) loads config and initializes handlers
3. Provider handler authenticates and fetches message IDs matching query
4. For each message:
   - Check `DBHandler.email_exists()` to avoid duplicates
   - Download raw MIME content
   - Optionally classify with `EmailClassifier.classify_email()`
   - Optionally extract metadata with `EmailExtractor.extract_metadata()`
   - Save .eml file with `utils.generate_filename()`
   - Optionally send to webhook with `utils.send_to_webhook()`
   - Record in database with `DBHandler.record_email()`
   - Update checkpoint with `DBHandler.save_checkpoint()`

## Important Implementation Details

### Path Resolution
All file paths must use the `core/paths.py` helpers to support sandboxed environments:
- Never hardcode paths like `~/.email-archiver` or `config/settings.yaml`
- Always use `get_data_dir()`, `get_config_path()`, etc.
- Use `resolve_path()` for user-provided relative paths

### LLM Provider Configuration
The system supports multiple LLM providers through a unified OpenAI-compatible interface:
- Priority: CLI args > config file > environment variables
- Local LLM detection: If `base_url` is set and doesn't contain "openai.com", use dummy API key
- See `EmailClassifier.__init__()` for resolution logic

### Incremental Sync
- Legacy checkpoint.json is migrated to database on first run (see `migrate_checkpoints_to_db()`)
- Checkpoints track last sync timestamp per provider
- Gmail uses `internalDate`, M365 uses `receivedDateTime`

### Filename Sanitization
- Emails are saved as `YYYYMMDD_HHMM_[Subject_Snippet]_[InternalID].eml`
- Subject lines are cleaned via `utils.generate_filename()` to remove illegal characters
- Optional `--rename` flag enables AI-powered clean filename generation

### Webhook Integration
- Webhook sends POST with multipart/form-data containing the .eml file
- Custom headers (including auth) configurable via settings.yaml or `--webhook-secret`
- Errors are logged but don't halt the sync process

## Testing Gmail/M365 Setup

To test provider authentication without a full sync:

```python
# Test Gmail
from email_archiver.core.gmail_handler import GmailHandler
config = load_config('config/settings.yaml')
handler = GmailHandler(config)
handler.authenticate()  # Should open browser or use existing token

# Test M365
from email_archiver.core.graph_handler import GraphHandler
handler = GraphHandler(config)
handler.authenticate()  # Should trigger device flow
```

## Common Gotchas

1. **OAuth Errors**: If authentication fails, delete tokens in `auth/` directory and re-authenticate
2. **Path Issues**: If running in a sandboxed environment, set `EESA_DATA_DIR` to a writable location (e.g., `/tmp`)
3. **Web UI Won't Start**: Check that optional dependencies are installed: `pip install ".[ui]"`
4. **LLM Classification Disabled**: Ensure API key is set via `LLM_API_KEY` or `--llm-api-key`
5. **Incremental Sync Starts Over**: Check that database exists at `EESA_DB_PATH` and isn't deleted between runs
