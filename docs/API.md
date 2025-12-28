# API Reference

## Command-Line Interface

### Main Command

```bash
uv run main.py [OPTIONS]
```

### Required Arguments

#### `--provider {gmail,m365}`
Specifies the email provider to use.

**Values:**
- `gmail` - Google Gmail
- `m365` - Microsoft 365 / Outlook

**Example:**
```bash
uv run main.py --provider gmail
```

### Optional Arguments

#### `--since YYYY-MM-DD`
Download emails received after the specified date.

**Format:** ISO date (YYYY-MM-DD)

**Example:**
```bash
uv run main.py --provider gmail --since 2024-01-01
```

#### `--after-id MESSAGE_ID`
Download emails received after a specific message ID.

**Note:** Implementation varies by provider. For precise control, use `--query` instead.

**Example:**
```bash
uv run main.py --provider gmail --after-id abc123xyz
```

#### `--message-id MESSAGE_ID`
Download a specific single email by its unique Message ID (overrides other filters).

**Example:**
```bash
uv run main.py --provider gmail --message-id 1934ad239c82
```

#### `--incremental`
Resume from the last checkpoint. Uses `config/checkpoint.json` to determine the starting point.

**Example:**
```bash
uv run main.py --provider gmail --incremental
```

#### `--query QUERY_STRING`
Custom search query using provider-specific syntax.

**Gmail syntax examples:**
```bash
# From specific sender
--query "from:sender@example.com"

# Subject contains text
--query "subject:Invoice"

# Has attachments
--query "has:attachment"

# Combine multiple criteria
--query "from:example.com subject:Report has:attachment"
```

**M365 syntax examples:**
```bash
# Use OData $search syntax
--query "subject:Invoice"
```

#### `--webhook-url URL`
Webhook endpoint URL to send downloaded `.eml` files to.

**Overrides:** `config/settings.yaml` webhook configuration

**Example:**
```bash
uv run main.py --provider gmail --since 2024-12-01 \
  --webhook-url https://api.example.com/emails
```

#### `--webhook-secret SECRET`
Authorization secret for webhook requests. Sets the `Authorization` header.

**Format:** Any string (typically "Bearer TOKEN" or just the token)

**Example:**
```bash
uv run main.py --provider gmail --since 2024-12-01 \
  --webhook-url https://api.example.com/emails \
  --webhook-secret "Bearer sk_live_abc123"
```

#### `--download-dir PATH`
Custom directory to save downloaded `.eml` files.

**Overrides:** `config/settings.yaml` app.download_dir setting

**Default:** `downloads/`

**Example:**
```bash
# Save to custom directory
uv run main.py --provider gmail --since 2024-12-01 \
  --download-dir /mnt/backup/emails
```

#### `--classify`
Enable AI-powered email classification using OpenAI.

**Example:**
```bash
email-archiver --provider gmail --classify --openai-api-key sk-...
```

#### `--openai-api-key KEY`
OpenAI API key for classification. Overrides the value in `settings.yaml`.

#### `--skip-promotional`
Automatically skip downloading emails classified as "promotional" or "social". Requires `--classify`.

#### `--metadata-output PATH`
Path to a JSONL file where classification metadata will be saved.

**Default:** `email_metadata.jsonl`

**Example:**
```bash
email-archiver --provider gmail --classify --metadata-output my_metadata.jsonl
```

#### `--llm-provider {openai,ollama,lm_studio,local}`
The LLM provider to use for classification.

- `openai`: (Default) Uses OpenAI's API. Requires `OPENAI_API_KEY`.
- `ollama`: Uses [Ollama](https://ollama.com/) (default URL: `http://localhost:11434/v1`).
- `lm_studio`: Uses [LM Studio](https://lmstudio.ai/) (default URL: `http://localhost:1234/v1`).
- `local`: Uses any OpenAI-compatible API (default URL: `http://localhost:8000/v1`).

#### `--llm-base-url URL`
Custom base URL for the LLM API. Use this if your local LLM is running on a non-standard port or hostname.

**Example:**
```bash
email-archiver --provider gmail --classify --llm-provider local --llm-base-url http://192.168.1.50:8080/v1
```

#### `--reset`
**FACTORY RESET**: Deletes all application data to start fresh.
- Wipes the SQLite database (`email_archiver.sqlite`).
- Dilutes the `downloads/` directory.
- Clears the log file (`sync.log`).
- **Preserves** authentication tokens in `auth/`.

**Example:**
```bash
email-archiver --reset
```

---

## Configuration File Reference

### `config/settings.yaml`

#### Gmail Configuration

```yaml
gmail:
  # Path to OAuth 2.0 client secrets file
  client_secrets_file: "config/client_secret.json"
  
  # OAuth scopes (read-only recommended)
  scopes: 
    - "https://www.googleapis.com/auth/gmail.readonly"
```

#### Microsoft 365 Configuration

```yaml
m365:
  # Azure AD Application (client) ID
  client_id: "YOUR_CLIENT_ID"
  
  # Authority URL (common for multi-tenant, or specific tenant ID)
  authority: "https://login.microsoftonline.com/common"
  
  # OAuth scopes
  scopes:
    - "Mail.Read"
```

#### Application Settings

```yaml
app:
  # Directory for downloaded .eml files
  download_dir: "downloads"
  
  # Log file path
  log_file: "sync.log"
```

#### Webhook Configuration

```yaml
webhook:
  # Webhook endpoint URL
  url: "https://your-webhook.com/endpoint"
  
  # Enable/disable webhook
  enabled: false
  
  # Optional HTTP headers (dictionary)
  headers:
    Authorization: "Bearer your-token"
    X-Custom-Header: "value"
```

---

## Python API Reference

### Core Modules

#### `core.gmail_handler.GmailHandler`

```python
class GmailHandler:
    def __init__(self, config: dict)
    def authenticate(self) -> None
    def fetch_ids(self, query: str = "") -> list
    def download_message(self, message_id: str) -> tuple[bytes, str]
```

**Methods:**

- `authenticate()`: Performs OAuth2 authentication
- `fetch_ids(query)`: Returns list of message objects matching query
- `download_message(message_id)`: Returns tuple of (email_content, internal_date)

#### `core.graph_handler.GraphHandler`

```python
class GraphHandler:
    def __init__(self, config: dict)
    def authenticate(self) -> None
    def fetch_ids(self, filter_str: str = None, search_str: str = None) -> list
    def download_message(self, message_id: str) -> bytes
```

**Methods:**

- `authenticate()`: Performs OAuth2 authentication
- `fetch_ids(filter_str, search_str)`: Returns list of message objects
- `download_message(message_id)`: Returns email content as bytes

#### `core.utils`

```python
def setup_logging(log_file: str = 'sync.log') -> None
def sanitize_filename(text: str) -> str
def generate_filename(subject: str, timestamp: datetime, internal_id: str = None) -> str
def send_to_webhook(file_path: str, url: str, headers: dict = None) -> None
```

**Functions:**

- `setup_logging()`: Configures logging to file and console
- `sanitize_filename()`: Removes illegal characters from filenames
- `generate_filename()`: Creates standardized .eml filename
- `send_to_webhook()`: Sends file to webhook endpoint

---

## Checkpoint File Format

### `config/checkpoint.json`

```json
{
  "gmail": {
    "last_internal_date": 1766478243000,
    "last_message_id": null
  },
  "m365": {
    "last_received_time": "2024-12-23T00:00:00Z",
    "last_message_id": null
  }
}
```

**Fields:**

- `gmail.last_internal_date`: Timestamp in milliseconds (Gmail internal date)
- `gmail.last_message_id`: Reserved for future use
- `m365.last_received_time`: ISO 8601 timestamp
- `m365.last_message_id`: Reserved for future use

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (authentication, API error, etc.) |
| 2 | Invalid arguments |

---

## Environment Variables

### `OAUTHLIB_INSECURE_TRANSPORT`

Set automatically by the application to allow HTTP for localhost OAuth callbacks.

**Value:** `1`

**Purpose:** Enables OAuth2 flow on localhost without HTTPS

---

## Logging

### Log Levels

- `INFO`: Normal operations (authentication, download progress)
- `WARNING`: Non-critical issues (rate limiting, retries)
- `ERROR`: Errors that prevent specific operations

### Log Format

```
YYYY-MM-DD HH:MM:SS,mmm - LEVEL - Message
```

### Example Log Output

```
2024-12-23 00:38:45,123 - INFO - Logging initialized.
2024-12-23 00:38:45,456 - INFO - Initialized gmail handler.
2024-12-23 00:38:45,789 - INFO - Gmail authentication successful.
2024-12-23 00:38:46,012 - INFO - Found 51 messages matching query: ''
2024-12-23 00:38:59,345 - INFO - Successfully sent email_file.eml to webhook.
2024-12-23 00:39:03,678 - INFO - Download complete. Processed 51 messages, Downloaded 10 new files.
```
