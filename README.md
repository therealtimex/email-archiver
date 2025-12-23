# Email-to-EML Secure Archiver (EESA)

A Python-based command-line utility to programmatically retrieve emails from **Gmail** and **Microsoft 365** and save them as RFC822-compliant `.eml` files.

## ✨ Features

- **🔐 Secure OAuth2 Authentication** - Browser-based authentication with 2FA support
- **📧 Multi-Provider Support** - Gmail and Microsoft 365 (Outlook)
- **🧠 AI-Powered Classification** - Automatically categorize emails and skip promotions (v0.3.0+)
- **🏠 Local LLM Support** - Connect to **Ollama**, **LM Studio**, or **llama.cpp** (v0.4.0+)
- **🔍 Advanced Filtering** - Date-based, incremental sync, custom queries
- **🪝 Webhook Integration** - Automatically send downloaded emails to webhook endpoints
- **💾 Incremental Checkpointing** - Resume interrupted downloads
- **📦 Modern Package Management** - UV/UVX support for easy installation and execution

## 🚀 Quick Start

### Installation

**Using uvx (recommended - no installation needed):**
```bash
uvx email-archiver --help
```

**Using pip:**
```bash
pip install email-archiver
email-archiver --help
```

**From source:**
```bash
git clone https://github.com/therealtimex/email-archiver
cd email-archiver
uv sync
uv run email-archiver --help
```

### Basic Usage

```bash
# Download emails from Gmail since a specific date
email-archiver --provider gmail --since 2024-12-01

# Incremental sync (resume from last checkpoint)
email-archiver --provider gmail --incremental

# AI Classification (OpenAI)
email-archiver --provider gmail --classify --openai-api-key "sk-..." --skip-promotional

# AI Classification (Local LLM via Ollama)
email-archiver --provider gmail --classify --llm-provider ollama --model "llama3"

# With webhook integration
email-archiver --provider gmail --since 2024-12-23 \
  --webhook-url https://your-webhook.com/endpoint \
  --webhook-secret "Bearer your-token"
```

## 📖 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get up and running in 5 minutes
- **[Complete Documentation](docs/README.md)** - Full setup and configuration guide
- **[API Reference](docs/API.md)** - Command-line arguments and Python API
- **[Examples](docs/EXAMPLES.md)** - 21 practical examples and use cases

## 🎯 Common Use Cases

### Daily Email Backup
```bash
email-archiver --provider gmail --incremental
```

### Archive Specific Emails
```bash
# Emails with attachments
email-archiver --provider gmail --query "has:attachment" --since 2024-01-01

# From specific sender
email-archiver --provider gmail --query "from:important@example.com"
```

### Webhook Integration
```bash
# Send emails to processing endpoint
email-archiver --provider gmail --incremental \
  --webhook-url https://api.example.com/emails \
  --webhook-secret "Bearer sk_live_abc123"
```

### Custom Download Directory
```bash
# Save to specific folder
email-archiver --provider gmail --since 2024-12-01 \
  --download-dir /path/to/backup/emails
```

## ⚙️ Configuration

### Gmail Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop App)
4. Save credentials as `config/client_secret.json`

### Microsoft 365 Setup

1. Register app in [Azure Portal](https://portal.azure.com/)
2. Add `Mail.Read` permission
3. Update `config/settings.yaml` with your Client ID

See [Quick Start Guide](docs/QUICKSTART.md) for detailed instructions.

## 🪝 Webhook Integration

EESA can automatically POST downloaded `.eml` files to a webhook endpoint:

**Via CLI:**
```bash
email-archiver --provider gmail --since 2024-12-01 \
  --webhook-url https://webhook.site/your-id \
  --webhook-secret "Bearer token"
```

**Via Configuration:**
```yaml
# config/settings.yaml
webhook:
  url: "https://your-webhook.com/endpoint"
  enabled: true
  headers:
    Authorization: "Bearer your-token"
```

## 📋 Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--provider {gmail,m365}` | Email provider (required) |
| `--since YYYY-MM-DD` | Download emails since date |
| `--incremental` | Resume from last checkpoint |
| `--query STRING` | Custom search query |
| `--webhook-url URL` | Webhook endpoint URL |
| `--webhook-secret SECRET` | Authorization header for webhook |
| `--download-dir PATH` | Custom download directory |
| `--classify` | Enable AI email classification |
| `--openai-api-key KEY` | OpenAI API key |
| `--skip-promotional` | Skip promotional/social emails |
| `--metadata-output PATH` | Path to save JSONL metadata |
| `--llm-provider ID` | LLM provider (openai, ollama, etc.) |
| `--llm-base-url URL` | Custom LLM API endpoint URL |

See [API Reference](docs/API.md) for complete documentation.

## 🔧 Requirements

- Python 3.9+
- Gmail API credentials (for Gmail)
- Azure AD app registration (for M365)

## 📁 Project Structure

```
email-archiver/
├── email_archiver/         # Main package
│   ├── main.py            # CLI entry point
│   └── core/              # Core modules
│       ├── gmail_handler.py
│       ├── graph_handler.py
│       └── utils.py
├── config/
│   ├── settings.yaml      # Configuration file
│   ├── checkpoint.json    # Incremental sync state
│   └── client_secret.json # OAuth credentials (git-ignored)
├── auth/                  # OAuth tokens (git-ignored)
├── downloads/             # Downloaded .eml files
├── docs/                  # Documentation
└── pyproject.toml         # Package configuration
```

## 🔒 Security

- **OAuth2 Only** - No password storage
- **Read-Only Scopes** - `gmail.readonly` and `Mail.Read`
- **Token Protection** - Tokens stored with restricted permissions (chmod 600)
- **HTTPS Webhooks** - Always use HTTPS for webhook endpoints

## 🤝 Contributing

This project follows the specification in `docs/SPECIFICATION.md`.

## 📄 License

See LICENSE file for details.

## 🆘 Support
y
For issues or questions:
1. Check the [documentation](docs/README.md)
2. Review [examples](docs/EXAMPLES.md)
3. Check logs in `sync.log`
4. Open an issue on [GitHub](https://github.com/therealtimex/email-archiver/issues)

## 🎓 Examples

### Automation with Cron
```bash
# Daily backup at 2 AM
0 2 * * * email-archiver --provider gmail --incremental
```

### Python Integration
```python
import subprocess

subprocess.run([
    "email-archiver",
    "--provider", "gmail",
    "--since", "2024-12-01"
])
```

### Using uvx (no installation)
```bash
# Run directly without installing
uvx email-archiver --provider gmail --since 2024-12-01

# Works from any directory
uvx email-archiver --help
```

See [EXAMPLES.md](docs/EXAMPLES.md) for 21 more examples!

---

## 👥 Author & Credits

**Author**: Trung Le  
**Team**: [RealTimeX.ai](https://realtimex.ai)  
**Repository**: https://github.com/therealtimex/email-archiver

---

**Built with ❤️ for secure email archiving**
