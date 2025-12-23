# Technical Specification: Email-to-EML Secure Archiver (EESA)

## 1. Project Overview
The **Email-to-EML Secure Archiver** is a Python-based command-line utility designed to programmatically retrieve emails from **Gmail** and **Microsoft 365** and save them as RFC822-compliant `.eml` files. The tool prioritizes security (OAuth2), flexibility (advanced filtering), and efficiency (incremental syncing).

---

## 2. Technical Stack
- **Language:** Python 3.9+
- **APIs:** 
    - Google Gmail API (via `google-api-python-client`)
    - Microsoft Graph API (via `requests` and `msal`)
- **Authentication:** OAuth 2.0 (Authorization Code Flow with PKCE)
- **State Management:** JSON-based checkpointing for incremental runs.
- **Dependencies:** `google-auth-oauthlib`, `msal`, `python-dateutil`, `tqdm` (for progress bars).

---

## 3. Functional Requirements

### 3.1 Authentication & 2FA
- **OAuth2 Integration:** The script must not store user passwords. It will use browser-based authentication to support 2FA and hardware keys.
- **Token Management:** 
    - Store refresh tokens locally in an `auth/` directory.
    - Implement automatic token refreshing to allow for long-running or scheduled tasks without re-authentication.

### 3.2 Filtering Engine
The utility must support the following filtering criteria:
- **Temporal:** `--since <YYYY-MM-DD>` (Download emails received after a specific date).
- **Sequential:** `--after-id <ID>` (Download emails received after a specific unique Message ID).
- **Incremental Sync:** `--incremental` (Automatically detect the last downloaded email and only fetch new items).
- **Advanced Search:** `--query <STRING>` (Support native provider syntax like `from:google.com` or `has:attachment`).

### 3.3 Download & Conversion Logic
- **Raw Data Fetching:** Request the "MIME" or "Raw" format from providers to ensure full header preservation (DKIM, SPF, IP hops).
- **Filename Sanitization:** Subject lines must be cleaned of OS-illegal characters (`/ \ : * ? " < > |`).
- **Standardized Naming:** Default format: `YYYYMMDD_HHMM_[Subject_Snippet]_[InternalID].eml`.

---

## 4. Logical Flow

### 4.1 Execution Process
1. **Initialize:** Load configuration (Provider, Client IDs, Directories).
2. **Authenticate:** Check for valid local tokens; if missing/expired, trigger OAuth2 browser flow.
3. **Query Construction:**
    - If `incremental` mode: Read `checkpoint.json` to find the last `receivedDateTime` or `internalDate`.
    - If `after-id` mode: Fetch the timestamp of that ID and set as the start point.
4. **Fetch Message List:** Retrieve a list of IDs matching the query.
5. **Batch Download:**
    - Loop through IDs.
    - Fetch raw content.
    - Save to disk.
    - Update `checkpoint.json` after every 10 successful downloads to prevent data loss on crash.

---

## 5. Directory Structure
```text
/email-archiver
│
├── main.py                 # CLI Entry point & orchestrator
├── core/
│   ├── gmail_handler.py    # Gmail API wrappers
│   ├── graph_handler.py    # MS Graph API wrappers
│   └── utils.py            # Filename cleaning & logging
│
├── config/
│   ├── settings.yaml       # API Client IDs & folder paths
│   └── checkpoint.json     # Stores "Last Downloaded" state
│
├── auth/
│   ├── gmail_token.json    # Local OAuth tokens (Git-ignored)
│   └── m365_token.json     # Local OAuth tokens (Git-ignored)
│
└── downloads/              # Default .eml output directory
```

---

## 6. Implementation Detail: Filtering Logic

| Feature | Gmail Implementation | M365 Implementation |
| :--- | :--- | :--- |
| **Since Date** | `q="after:YYYY/MM/DD"` | `$filter=receivedDateTime ge YYYY-MM-DD...` |
| **After ID** | 1. Get `internalDate` of ID.<br>2. `q="after:{timestamp}"` | 1. Get `receivedDateTime` of ID.<br>2. `$filter=receivedDateTime gt {timestamp}` |
| **Search Query** | Passed directly to `q=` | Passed to `$search=` |

---

## 7. Non-Functional Requirements
- **Rate Limiting:** Implement exponential backoff if the API returns `429 Too Many Requests`.
- **Idempotency:** The script should check if a file already exists (via Message-ID mapping) before downloading to save bandwidth.
- **Logging:** Maintain a `sync.log` file tracking successful downloads and any failed attempts (e.g., connectivity issues).
- **Security:** Use `chmod 600` on the `auth/` directory to restrict token access to the local user.

---

## 8. Usage Examples

**Download all emails since Jan 2024:**
```bash
python main.py --provider gmail --since 2024-01-01
```

**Resume from last run (Incremental):**
```bash
python main.py --provider outlook --incremental
```

**Targeted search for invoices:**
```bash
python main.py --provider gmail --query "subject:Invoice filename:pdf"
```


