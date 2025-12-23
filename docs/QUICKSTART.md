# Quick Start Guide

## Installation

```bash
cd email-archiver
uv sync
```

## Gmail Quick Start

### 1. Set up Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Gmail API
3. Create OAuth 2.0 credentials (Desktop App)
4. Download and save as `config/client_secret.json`

### 2. Run your first archive

```bash
# Download emails from the last week
uv run main.py --provider gmail --since 2024-12-16
```

### 3. Authentication

When prompted:
1. Open the URL shown in your terminal
2. Sign in to your Google account
3. Copy the authorization code
4. Paste it back into the terminal

### 4. Check results

```bash
ls downloads/
cat sync.log
```

## Microsoft 365 Quick Start

### 1. Set up Azure AD credentials

1. Go to [Azure Portal](https://portal.azure.com/)
2. Register an app in Azure AD
3. Add Mail.Read permission
4. Copy the Client ID

### 2. Update configuration

Edit `config/settings.yaml`:
```yaml
m365:
  client_id: "YOUR_CLIENT_ID_HERE"
```

### 3. Run your first archive

```bash
uv run main.py --provider m365 --since 2024-12-16
```

## Webhook Quick Start

### Test with webhook.site

```bash
# Get a test URL from https://webhook.site
uv run main.py --provider gmail --since 2024-12-23 \
  --webhook-url https://webhook.site/YOUR-UNIQUE-ID
```

### Production webhook

```bash
uv run main.py --provider gmail --incremental \
  --webhook-url https://your-api.com/emails \
  --webhook-secret "Bearer your-secret-token"
```

## Common Use Cases

### Daily backup (cron job)

```bash
# Add to crontab
0 2 * * * cd /path/to/email-archiver && uv run main.py --provider gmail --incremental
```

### Archive specific sender

```bash
uv run main.py --provider gmail --query "from:important@example.com"
```

### Archive with attachments only

```bash
uv run main.py --provider gmail --query "has:attachment" --since 2024-01-01
```

## Next Steps

- Read the [full documentation](README.md)
- Configure webhook integration
- Set up automated backups
- Explore advanced filtering options
