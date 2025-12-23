# Examples

## Basic Usage Examples

### Example 1: Download Recent Emails from Gmail

```bash
# Download all emails from the last 7 days
uv run main.py --provider gmail --since 2024-12-16
```

**Expected Output:**
```
2024-12-23 10:00:00,123 - INFO - Logging initialized.
2024-12-23 10:00:00,456 - INFO - Initialized gmail handler.
2024-12-23 10:00:05,789 - INFO - Gmail authentication successful.
2024-12-23 10:00:06,012 - INFO - Found 42 messages matching query: 'after:2024/12/16'
100%|████████████████████████████████████| 42/42 [00:25<00:00,  1.65it/s]
2024-12-23 10:00:31,234 - INFO - Download complete. Processed 42 messages, Downloaded 42 new files.
```

### Example 2: Incremental Sync

```bash
# First run - downloads all emails
uv run main.py --provider gmail --since 2024-01-01

# Subsequent runs - only downloads new emails
uv run main.py --provider gmail --incremental
```

### Example 3: Microsoft 365 with Date Filter

```bash
uv run main.py --provider m365 --since 2024-12-01
```

---

## Advanced Filtering Examples

### Example 4: Emails from Specific Sender

```bash
# Gmail
uv run main.py --provider gmail --query "from:notifications@github.com"

# M365 (using $search)
uv run main.py --provider m365 --query "from:notifications@github.com"
```

### Example 5: Emails with Attachments

```bash
uv run main.py --provider gmail --query "has:attachment" --since 2024-12-01
```

### Example 6: Subject-Based Search

```bash
# Find all invoices
uv run main.py --provider gmail --query "subject:Invoice OR subject:Receipt"

# Find security alerts
uv run main.py --provider gmail --query "subject:Alert is:important"
```

### Example 7: Complex Query

```bash
# Emails from specific domain with attachments, last 30 days
uv run main.py --provider gmail \
  --query "from:@company.com has:attachment" \
  --since 2024-11-23
```

### Example 8: Custom Download Directory

```bash
# Save to specific backup location
uv run main.py --provider gmail --since 2024-12-01 \
  --download-dir /mnt/backup/emails/gmail

# Organize by date
uv run main.py --provider gmail --incremental \
  --download-dir ./archive/$(date +%Y-%m-%d)

# Network storage
uv run main.py --provider m365 --since 2024-12-01 \
  --download-dir /Volumes/NAS/email-backups
```

### Example 10: AI-Powered Classification

```bash
# Classify emails and skip promotions
email-archiver --provider gmail --since 2024-12-01 \
  --classify --openai-api-key "sk-..." \
  --skip-promotional
```

### Example 11: Comprehensive Metadata Export

```bash
# Export metadata to a custom file
email-archiver --provider gmail --incremental \
  --classify \
  --metadata-output data/email_analysis.jsonl
```

### Example 12: Local LLM with Ollama

```bash
# Use Ollama for free, local classification
# Ensure Ollama is running: ollama run llama3
email-archiver --provider gmail --classify \
  --llm-provider ollama --model "llama3" \
  --skip-promotional
```

### Example 13: Local LLM with LM Studio

```bash
# Use LM Studio local server
email-archiver --provider gmail --classify \
  --llm-provider lm_studio --model "mistral-7b"
```

---

## Webhook Integration Examples

### Example 14: Basic Webhook

```bash
uv run main.py --provider gmail --since 2024-12-23 \
  --webhook-url https://webhook.site/abc-123-def
```

### Example 9: Webhook with Authentication

```bash
uv run main.py --provider gmail --incremental \
  --webhook-url https://api.example.com/emails/ingest \
  --webhook-secret "Bearer sk_live_abc123xyz"
```

### Example 10: Webhook via Configuration File

Edit `config/settings.yaml`:
```yaml
webhook:
  url: "https://api.example.com/emails/ingest"
  enabled: true
  headers:
    Authorization: "Bearer sk_live_abc123xyz"
    X-API-Key: "your-api-key"
    X-Source: "email-archiver"
```

Then run:
```bash
uv run main.py --provider gmail --incremental
```

---

## Automation Examples

### Example 11: Daily Backup Script

Create `backup.sh`:
```bash
#!/bin/bash
cd /path/to/email-archiver

# Run incremental backup
uv run main.py --provider gmail --incremental

# Check exit code
if [ $? -eq 0 ]; then
    echo "Backup completed successfully"
else
    echo "Backup failed" >&2
    exit 1
fi
```

Make it executable and add to cron:
```bash
chmod +x backup.sh

# Add to crontab (runs daily at 2 AM)
crontab -e
# Add line:
0 2 * * * /path/to/email-archiver/backup.sh >> /var/log/email-backup.log 2>&1
```

### Example 12: Multi-Provider Backup

Create `backup-all.sh`:
```bash
#!/bin/bash
cd /path/to/email-archiver

# Backup Gmail
echo "Backing up Gmail..."
uv run main.py --provider gmail --incremental

# Backup M365
echo "Backing up M365..."
uv run main.py --provider m365 --incremental

echo "All backups complete"
```

### Example 13: Selective Backup with Webhook

```bash
#!/bin/bash
# Backup important emails and send to processing webhook

uv run main.py --provider gmail \
  --query "is:important OR from:boss@company.com" \
  --incremental \
  --webhook-url https://api.company.com/process-important-emails \
  --webhook-secret "Bearer $WEBHOOK_TOKEN"
```

---

## Integration Examples

### Example 14: Python Script Integration

```python
import subprocess
import json

def backup_emails(provider, since_date):
    """Run email archiver and return results"""
    cmd = [
        "uv", "run", "main.py",
        "--provider", provider,
        "--since", since_date
    ]
    
    result = subprocess.run(
        cmd,
        cwd="/path/to/email-archiver",
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"Success: {result.stdout}")
        return True
    else:
        print(f"Error: {result.stderr}")
        return False

# Usage
backup_emails("gmail", "2024-12-01")
```

### Example 15: Webhook Receiver (Flask)

```python
from flask import Flask, request
import os

app = Flask(__name__)

@app.route('/emails/ingest', methods=['POST'])
def receive_email():
    # Verify authorization
    auth_header = request.headers.get('Authorization')
    if auth_header != 'Bearer sk_live_abc123xyz':
        return {'error': 'Unauthorized'}, 401
    
    # Get the uploaded file
    if 'file' not in request.files:
        return {'error': 'No file provided'}, 400
    
    file = request.files['file']
    
    # Save to processing directory
    filepath = os.path.join('/data/emails', file.filename)
    file.save(filepath)
    
    # Process the email (your custom logic here)
    process_email(filepath)
    
    return {'status': 'success', 'filename': file.filename}, 200

def process_email(filepath):
    # Your email processing logic
    print(f"Processing {filepath}")

if __name__ == '__main__':
    app.run(port=5000)
```

### Example 16: Webhook Receiver (Node.js/Express)

```javascript
const express = require('express');
const multer = require('multer');
const path = require('path');

const app = express();
const upload = multer({ dest: '/data/emails/' });

app.post('/emails/ingest', upload.single('file'), (req, res) => {
    // Verify authorization
    const authHeader = req.headers.authorization;
    if (authHeader !== 'Bearer sk_live_abc123xyz') {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    
    if (!req.file) {
        return res.status(400).json({ error: 'No file provided' });
    }
    
    console.log(`Received email: ${req.file.originalname}`);
    
    // Process the email
    processEmail(req.file.path);
    
    res.json({ 
        status: 'success', 
        filename: req.file.originalname 
    });
});

function processEmail(filepath) {
    // Your email processing logic
    console.log(`Processing ${filepath}`);
}

app.listen(5000, () => {
    console.log('Webhook server listening on port 5000');
});
```

---

## Troubleshooting Examples

### Example 17: Debug Mode with Verbose Logging

```bash
# Check what's happening during authentication
uv run main.py --provider gmail --since 2024-12-23 2>&1 | tee debug.log

# Review the log
cat debug.log
cat sync.log
```

### Example 18: Test Webhook Connectivity

```bash
# Use webhook.site to verify webhook is working
uv run main.py --provider gmail --since 2024-12-23 \
  --webhook-url https://webhook.site/YOUR-UNIQUE-ID

# Then check https://webhook.site/YOUR-UNIQUE-ID to see the received files
```

### Example 19: Small Test Run

```bash
# Test with just today's emails
uv run main.py --provider gmail --since $(date +%Y-%m-%d)

# Or specific query with limited results
uv run main.py --provider gmail --query "from:test@example.com"
```

---

## Performance Examples

### Example 20: Parallel Provider Backups

```bash
# Run both providers in parallel (separate terminals or background jobs)
uv run main.py --provider gmail --incremental &
GMAIL_PID=$!

uv run main.py --provider m365 --incremental &
M365_PID=$!

# Wait for both to complete
wait $GMAIL_PID
wait $M365_PID

echo "Both backups complete"
```

### Example 21: Rate-Limited Backup

```bash
# For large mailboxes, use date ranges to avoid rate limits
for month in {01..12}; do
    echo "Backing up 2024-${month}"
    uv run main.py --provider gmail --since 2024-${month}-01 --query "after:2024/${month}/01 before:2024/${month}/31"
    sleep 60  # Wait 1 minute between batches
done
```
