# Email-to-EML Secure Archiver (EESA) - Documentation

## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Usage](#usage)
5. [Webhook Integration](#webhook-integration)
6. [Advanced Features](#advanced-features)
7. [Troubleshooting](#troubleshooting)

---

## Overview

The Email-to-EML Secure Archiver (EESA) is a Python-based command-line utility that retrieves emails from Gmail and Microsoft 365 and saves them as RFC822-compliant `.eml` files.

### Key Features
- **OAuth2 Authentication**: Secure browser-based authentication with 2FA support
- **Multiple Providers**: Gmail and Microsoft 365 (Outlook)
- **Advanced Filtering**: Date-based, incremental sync, custom queries
- **Webhook Integration**: Automatically send downloaded emails to a webhook endpoint
- **Checkpointing**: Resume interrupted downloads
- **UV/UVX Support**: Modern Python package management

---

## Installation

### Prerequisites
- Python 3.9 or higher
- `uv` package manager (recommended) or `pip`

### Using UV (Recommended)
```bash
cd email-archiver
uv sync
```

### Using pip
```bash
cd email-archiver
pip install -r requirements.txt
```

---

## Configuration

### Gmail Setup

1. **Create Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the **Gmail API**

2. **Create OAuth 2.0 Credentials**
   - Navigate to "Credentials" → "Create Credentials" → "OAuth client ID"
   - Choose "Desktop app" as the application type
   - Download the credentials JSON file

3. **Configure EESA**
   - Save the downloaded file as `config/client_secret.json`
   - Or update the path in `config/settings.yaml`:
     ```yaml
     gmail:
       client_secrets_file: "config/client_secret.json"
       scopes: ["https://www.googleapis.com/auth/gmail.readonly"]
     ```

### Microsoft 365 Setup

1. **Register Application in Azure AD**
   - Go to [Azure Portal](https://portal.azure.com/)
   - Navigate to "Azure Active Directory" → "App registrations"
   - Click "New registration"
   - Set redirect URI to `http://localhost` (for desktop apps)

2. **Configure Permissions**
   - Add "Mail.Read" delegated permission
   - Grant admin consent if required

3. **Update Configuration**
   - Copy the Application (client) ID
   - Update `config/settings.yaml`:
     ```yaml
     m365:
       client_id: "YOUR_CLIENT_ID"
       authority: "https://login.microsoftonline.com/common"
       scopes: ["Mail.Read"]
     ```

### Settings File

The `config/settings.yaml` file contains all configuration options:

```yaml
gmail:
  client_secrets_file: "config/client_secret.json"
  scopes: ["https://www.googleapis.com/auth/gmail.readonly"]

m365:
  client_id: "YOUR_CLIENT_ID"
  authority: "https://login.microsoftonline.com/common"
  scopes: ["Mail.Read"]

app:
  download_dir: "downloads"
  log_file: "sync.log"

webhook:
  url: ""
  enabled: false
  headers: {}
```

---

## Usage

### Basic Commands

**Download all emails since a specific date:**
```bash
uv run main.py --provider gmail --since 2024-01-01
```

**Resume from last checkpoint (incremental sync):**
```bash
uv run main.py --provider m365 --incremental
```

**Search with custom query:**
```bash
uv run main.py --provider gmail --query "subject:Invoice has:attachment"
```

### Command-Line Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--provider` | Email provider (gmail or m365) | `--provider gmail` |
| `--since` | Download emails since date (YYYY-MM-DD) | `--since 2024-01-01` |
| `--after-id` | Download emails after specific message ID | `--after-id abc123` |
| `--incremental` | Resume from last checkpoint | `--incremental` |
| `--query` | Custom search query | `--query "from:example.com"` |
| `--webhook-url` | Webhook URL to send files to | `--webhook-url https://...` |
| `--webhook-secret` | Authorization header for webhook | `--webhook-secret "Bearer token"` |

### Query Syntax

**Gmail:**
- `from:sender@example.com` - Emails from specific sender
- `subject:Invoice` - Emails with "Invoice" in subject
- `has:attachment` - Emails with attachments
- `after:2024/01/01` - Emails after date
- `is:unread` - Unread emails

**Microsoft 365:**
- Uses OData `$filter` syntax
- `from/emailAddress/address eq 'sender@example.com'`
- `receivedDateTime ge 2024-01-01T00:00:00Z`

---

## Webhook Integration

EESA can automatically send downloaded `.eml` files to a webhook endpoint.

### Configuration Methods

**Method 1: Configuration File**

Edit `config/settings.yaml`:
```yaml
webhook:
  url: "https://your-webhook.com/endpoint"
  enabled: true
  headers:
    Authorization: "Bearer your-token-here"
```

**Method 2: Command-Line Arguments**

```bash
uv run main.py --provider gmail --since 2024-12-01 \
  --webhook-url https://your-webhook.com/endpoint \
  --webhook-secret "Bearer your-token-here"
```

### Webhook Payload

The `.eml` file is sent as a multipart/form-data POST request:
- **Field name**: `file`
- **Content-Type**: `message/rfc822`
- **Filename**: Original `.eml` filename

### Testing Webhooks

Use [webhook.site](https://webhook.site) for testing:

```bash
uv run main.py --provider gmail --since 2024-12-23 \
  --webhook-url https://webhook.site/YOUR-UNIQUE-ID
```

---

## Advanced Features

### Incremental Sync

EESA maintains a checkpoint file (`config/checkpoint.json`) to track the last downloaded email:

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

Use `--incremental` to automatically resume from the last checkpoint.

### Filename Format

Downloaded files follow this naming convention:
```
YYYYMMDD_HHMM_[Subject_Snippet]_[MessageID].eml
```

Example:
```
20241223_1430_Invoice_December_2024_a1b2c3d4.eml
```

### Logging

All operations are logged to `sync.log`:
- Authentication events
- Download progress
- Webhook delivery status
- Errors and warnings

---

## Troubleshooting

### Authentication Issues

**Problem**: `MismatchingStateError` during OAuth flow

**Solution**: The tool now uses manual console flow. Copy the authorization code from the browser and paste it into the terminal.

**Problem**: `FileNotFoundError: Client secrets file not found`

**Solution**: Ensure `config/client_secret.json` exists or update the path in `settings.yaml`.

### Gmail API Issues

**Problem**: `403 Forbidden - Gmail API has not been used in project`

**Solution**: 
1. Visit the URL in the error message
2. Click "Enable API"
3. Wait a few minutes for propagation
4. Retry the command

### Webhook Issues

**Problem**: Webhook delivery fails

**Solution**:
- Check the webhook URL is accessible
- Verify the authorization header/secret is correct
- Check `sync.log` for detailed error messages
- Test with webhook.site first

### Rate Limiting

**Problem**: `429 Too Many Requests`

**Solution**: The tool implements exponential backoff automatically. If you encounter persistent rate limiting:
- Use more specific queries to reduce the number of emails fetched
- Add delays between runs
- Check your API quota in Google Cloud Console

---

## Output Structure

```
email-archiver/
├── downloads/          # Downloaded .eml files
├── auth/              # OAuth tokens (git-ignored)
│   ├── gmail_token.json
│   └── m365_token.json
├── config/
│   ├── settings.yaml
│   ├── checkpoint.json
│   └── client_secret.json
└── sync.log           # Application logs
```

---

## Security Considerations

1. **Token Storage**: OAuth tokens are stored in `auth/` with restricted permissions (chmod 600)
2. **Git Ignore**: Ensure `auth/` and sensitive config files are in `.gitignore`
3. **API Scopes**: Uses read-only scopes (`gmail.readonly`, `Mail.Read`)
4. **Webhook Security**: Always use HTTPS for webhook URLs and include authentication headers

---

## Support

For issues or questions:
1. Check the logs in `sync.log`
2. Review this documentation
3. Verify your API credentials and permissions
4. Test with a small date range first (`--since` with recent date)
