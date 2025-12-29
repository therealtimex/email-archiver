# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.4] - 2025-12-28

### Fixed
- **Read-Only File System Error**: Fixed `[Errno 30] Read-only file system: 'email_metadata.jsonl'` error when running in containerized or sandboxed environments (e.g., RealTimeX local apps). Metadata file now writes to the data directory instead of the current working directory, which may be read-only.

## [1.3.3] - 2025-12-28

### Fixed
- **Sync Crash on Early Failure**: Fixed `UnboundLocalError: cannot access local variable 'current_gmail_checkpoint'` that occurred when sync failed before the download loop started. Checkpoint variables are now initialized early to ensure they're always available in the cleanup (finally) block.

## [1.3.2] - 2025-12-28

### Changed
- **Browser Auto-Open Disabled by Default**: The Web UI no longer automatically opens a browser window when starting with `--ui`. This is better for server deployments, remote usage, and uvx installations. Use `--browser` flag to enable auto-open: `email-archiver --ui --browser`.

## [1.3.1] - 2025-12-28

### Fixed
- **MIME Header Decoding**: Fixed email subjects, senders, and recipients with special characters (Vietnamese, Chinese, emoji, etc.) being stored in raw MIME-encoded format. The system now properly decodes RFC 2047 headers (e.g., `=?UTF-8?B?...?=`) to readable text. This fixes display issues in the Web UI, database, and filenames for international emails.

## [1.3.0] - 2025-12-28

### Added
- **Specific Email Archival**: Added `--message-id` CLI argument to download a single email by its unique ID, overriding other filters.
- **Metadata Output Path**: Added `--metadata-output` argument to specify custom path for metadata JSONL file.
- **Smart LLM Error Handling**: Implemented intelligent error classification for LLM failures with circuit breaker pattern:
  - Distinguishes between network errors, auth failures, rate limits, server errors, and parsing issues
  - Fast failure detection: Disables LLM after 2 network errors (vs. 60s timeout × N emails)
  - Auto-retry with exponential backoff for rate limiting (429 errors)
  - Continues archiving emails even when LLM fails
  - Health check before sync starts to fail fast on unreachable endpoints
  - Detailed statistics reporting at end of sync
  - Graceful degradation: Only disables AI features when truly unavailable
- **AI Processing Status Tracking in Database**: Added columns to track AI processing status for each email:
  - `ai_classification_status`: Tracks success/failed/disabled/skipped for classification
  - `ai_extraction_status`: Tracks success/failed/disabled/skipped for extraction
  - `ai_processing_error`: Stores error message when AI processing fails
  - `ai_processed_at`: Timestamp of AI processing attempt
  - New methods: `get_emails_by_ai_status()` and `get_ai_stats()` for querying failed emails
  - Automatic migration for existing databases
- **Retry AI Processing**: Added `--retry-ai` command to reprocess emails that previously failed AI classification/extraction:
  - Queries database for emails with failed/disabled AI status
  - Prompts user for confirmation before reprocessing
  - Useful for retrying after fixing LLM configuration or network issues
- **Configurable LLM Timeout**: Added `--llm-timeout` argument to customize API timeout (default: 60 seconds):
  - Allows faster failure detection in unreliable network environments
  - Can be set lower (e.g., 10s) for local LLMs or higher for slow cloud providers
- **Fallback Rule-Based Classification**: When LLM is disabled, system now uses basic rule-based classification:
  - Detects newsletters by checking for "Unsubscribe" links and List-Unsubscribe headers
  - Categorizes emails with common promotional keywords
  - Ensures emails still get basic categorization even when AI is unavailable
- **Web UI: LLM Status Monitoring**: Added real-time LLM health status to the dashboard:
  - Live status indicator (🟢 Online / 🔴 Offline / ⚠️ Error)
  - Displays endpoint URL and model name
  - Warning banner when LLM is unreachable
  - Automatic health check on page load and every 2 seconds
  - Click to retry connectivity test
- **Web UI: AI Success Rate Display**: Added AI processing statistics to the dashboard:
  - Classification success/failure counts
  - Extraction success/failure counts
  - Visual display of AI processing reliability
  - Updates in real-time during sync operations

### Fixed
- **Gmail Message-ID Search**: Fixed `--message-id` to correctly use `rfc822msgid:` operator for Message-ID headers (containing `@`), and direct fetch for Gmail internal IDs. Previous implementation used invalid `id:` operator that returned 0 results.
- **LLM Timeout UX**: Dramatically improved user experience when LLM endpoint is unreachable (e.g., network change, VPN disconnect). Previously waited 60s × number of emails; now detects and disables after ~10 seconds.
- **Database Migration Order**: Fixed initialization sequence to run AI status column migration before creating indexes, preventing errors when upgrading from older database schemas.

## [1.2.7] - 2025-12-27

### Added
- **File Download**: Added ability to download raw `.eml` files directly from the Web Dashboard.

## [1.2.6] - 2025-12-27

### Fixed
- **Release Automation**: Retry release triggering to resolve CI pipeline issues.

## [1.2.5] - 2025-12-27

### Fixed
- **CI/CD**: Added `workflow_dispatch` to the release workflow to allow manual triggering of releases from the GitHub Actions tab.

## [1.2.4] - 2025-12-27

### Added
- **UI Tooltips**: Added informative tooltips to the dashboard settings to explain synchronization options (Incremental, AI Classify, Deep Extract, etc.).

### Changed
- **Dependencies**: Updated project dependencies.
- **Pagination**: Improved pagination logic in the dashboard.

## [1.2.3] - 2025-12-27

### Fixed
- **Post-Reset Authenticated Sync**: Fixed an issue where sync would fail after a factory reset (or in token-only environments) because the backend strictly required `credentials.json` even if a valid `token.json` was present. Now checks for *either* credentials *or* valid tokens.

## [1.2.2] - 2025-12-27

### Fixed
- **CLI Factory Reset**: Fixed `NameError` crashes (missing `sys` and `get_db_path` imports) when running `email-archiver --reset`.

## [1.2.0] - 2025-12-27

### Added
- **LLM Optimization**: Implemented a comprehensive optimization suite for AI classification and extraction, significantly improving performance with local models (Llama 3, Mistral) and reducing token usage.
    - **Content Cleaning**: New `ContentCleaner` utility removes footers, legal disclaimers, and deep reply chains to reduce noise.
    - **Markdown Conversion**: Automatically converts HTML emails to lightweight Markdown structure (preserving headers, lists, and links) for better semantic understanding by LLMs.
    - **HTML Fallback**: Added support for processing HTML-only emails (common in newsletters) by stripping tags and converting to text.
    - **Prompt Engineering**: Restructured prompts to be "Local LLM Friendly" with explicit schema instructions at the end of the prompt.
    - **Metadata Signals**: The classifier now utilizes `List-Unsubscribe`, `X-Priority`, and `Importance` headers as additional signals.

## [1.1.1] - 2025-12-26

### Fixed
- **Documentation**: Updated CLI documentation in `README.md` and `docs/API.md` to include the missing `--reset` (Factory Reset) flag.

## [1.1.0] - 2025-12-26

### Added
- **Factory Reset**: Added a new `--reset` CLI flag that allows users to perform a complete factory reset. This wipes the database, logs, and downloads directory to provide a clean slate for resolving rigorous data issues, while preserving authentication tokens.
- **UI "Danger Zone"**: Introduced a "Danger Zone" in the Settings dashboard with a Factory Reset capability, featuring a confirmation modal to prevent accidental data loss.

## [1.0.0] - 2025-12-26

### 🚀 Major Release
- **First Stable Desktop Release**: This release marks the official v1.0 milestone for local desktop usage, featuring critical security hardening and stability improvements.

### 🔒 Security
- **CORS Restriction**: Restricted API access to `localhost` and `127.0.0.1` to prevent unauthorized access from external websites.
- **Webhook Validation**: Implemented strict validation for webhook URLs to block private/internal IP addresses (SSRF prevention).
- **Path Validation**: Added strict validation for all file paths to prevent arbitrary file system access outside allowed directories (e.g., User Home).

### 🛠 Stability
- **API Timeouts**: Added explicit timeouts to all external API calls (Microsoft Graph, OpenAI) to prevent the application from hanging.
- **Robust File Handling**: Implemented try-finally blocks for metadata file operations to ensure file handles are properly closed and to prevent data corruption.

### Fixed
- **Robust JSON Parsing**: Enhanced the AI response parser to handle LLM outputs containing C-style comments (`//`). This improves resilience when using local LLMs that append explanatory comments to their JSON responses.

## [0.8.17] - 2025-12-26

### Fixed
- **Local Re-analysis Robustness**: Fixed an ID mapping mismatch that caused local files to be skipped during re-analysis. The sync process now correctly preserves existing file paths in local-only mode, ensuring clean updates without duplicate files.

## [0.8.16] - 2025-12-26

### Fixed
- **Local Re-analysis**: Resolved an issue where local archives were skipped during re-analysis. The sync process now correctly performs full AI classification and extraction on local `.eml` files and updates the database records on conflict.

## [0.8.15] - 2025-12-26

### Fixed
- **UI Accessibility**: Moved the "Re-analyze Local Archive" button to a dedicated position below the SYNC button group to prevent click-blocking from absolute-positioned glow effects.
- **CLI Guidance**: Clarified that the correct command is `email-archiver` (hyphenated) as defined in `pyproject.toml`.

## [0.8.14] - 2025-12-26

### Added
- **Re-analyze Local Archive**: Added a new feature to the Web Dashboard and API to re-process locally archived emails. This allows users to re-run AI classification, extraction, Slugs renaming, and metadata embedding using new models (e.g., GPT-5) or refined settings without re-fetching data from email providers.

## [0.8.13] - 2025-12-26

### Removed
- **CLI Help Cleanup**: Suppressed the legacy `--openai-api-key` argument from the terminal help output. The flag remains functional for backward compatibility but is no longer advertised in favor of the unified `--llm-api-key`.

## [0.8.12] - 2025-12-26

### Fixed
- **Robust JSON Parsing**: Introduced a sophisticated JSON parsing helper that automatically handles markdown code blocks and extra text in LLM responses. This significantly improves reliability when using local LLM providers like **LM Studio** and **Ollama**.
- **Enhanced Logging**: Added raw response logging when JSON parsing fails to facilitate easier troubleshooting and debugging.

## [0.8.11] - 2025-12-26

### Changed
- **Sync Engine UI Redesign**: Removed collapsibility of "Advanced Filters" in the Web Dashboard. Critical configurations like **Since Date**, **After ID**, and **Search Query** are now always visible and better integrated into the layout for improved accessibility.

## [0.8.10] - 2025-12-26

### Fixed
- **LLM Compatibility**: Made `response_format` conditional to ensure compatibility with local LLM providers like **LM Studio** and **Ollama**, which may not support the `json_object` type.
- **Improved Robustness**: The system now automatically detects the backend type and adjusts the API call parameters accordingly.

## [0.8.9] - 2025-12-26

### Fixed
- **Sync Hotfix**: Fixed an `AttributeError` in the Web Dashboard sync task caused by missing LLM fields in the `SyncRequest` model.
- **Frontend Sync**: Ensured the dashboard correctly transmits LLM configuration (Base URL, API Key, Model) when triggering a sync.

## [0.8.8] - 2025-12-26

### Changed
- **Full LLM Standardization**: Removed the redundant `PROVIDER` dependency. LLM configuration is now purely driven by **Base URL**, **API Key**, and **Model**.
- **Simplified UI**: Replaced the Provider dropdown in settings with quick **Presets** (OpenAI, Ollama, LM Studio) for a faster setup experience.
- **Backend Refinement**: Core inference logic now automatically detects local vs. cloud providers based on the Base URL, making the API key optional for local endpoints.

## [0.8.7] - 2025-12-26

### Added
- **Dashboard Feature Parity**: Added full UI support for `--rename` (intelligent file renaming) and `--embed` (AI metadata embedding) features.
- **Enhanced Sync Engine**: Dashboard now allows granular control over advanced archiving features through a modernized toggle interface.

## [0.8.6] - 2025-12-26

### Changed
- **UI Modernization**: Updated the Web Dashboard settings page to use standardized "LLM API Key" labeling and internal field mappings (`api_key`).
- **Standardization Alignment**: Synchronized UI state with the backend's new LLM configuration standard.

## [0.8.5] - 2025-12-26

### Changed
- **Standardized LLM Config**: Unified LLM configuration via `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` environment variables and CLI flags. 
- **Universal Provider Support**: Improved support for custom LLM providers (Ollama, LM Studio, etc.) by prioritizing the new standardized configuration over legacy provider-specific settings.

## [0.8.4] - 2025-12-26

### Added
- **Intelligent Renaming**: Added `--rename` flag to slugify filenames (lowercase, hyphen-separated), resolving potential crashes in downstream systems.
- **X-Header Embedding**: Added `--embed` flag to inject AI-generated metadata (Category, Summary, Sentiment, Entities) directly into `.eml` headers.
- **MIME Persistence**: The complete raw AI output is now embedded as a Base64-encoded `X-EESA-Raw-JSON` header, making `.eml` files standalone units of work for `crm-automator`.

## [0.8.3] - 2025-12-26

### Added
- **Sandbox & Restricted Environment Support**: Introduced `EESA_DATA_DIR` and granular environment variable overrides (`EESA_DB_PATH`, `EESA_LOG_FILE`, etc.) to support running in read-only or restricted file systems.
- **Improved UX for `uvx`**: Set the default data directory to `~/.email-archiver`, providing a seamless "zero-config" experience while ensuring data persistence.
- **Stdout Logging**: Support for redirecting logs to `stdout` or `stderr` via `EESA_LOG_FILE`, ideal for containerized or serverless environments.

## [0.8.2] - 2025-12-23

## [0.8.1] - 2025-12-23

### Fixed
- **Persistence Logic**: Unified configuration path resolution between the UI and CLI to ensure settings changes are always correctly applied.
- **Database Path Healing**: The database now automatically updates the file location of an archived email if it is moved or re-downloaded to a new folder, resolving "IntegrityError" warnings.
- **Improved Logging**: Added explicit logging of the active download directory at the start of every sync.

## [0.8.0] - 2025-12-23

### Fixed
- **Path Migration**: Fixed a regression where changing the download folder would not correctly re-populate the new folder. The app now correctly identifies missing files within the current sync scope.

## [0.7.9] - 2025-12-23

### Added
- **Smart Sync**: Implemented dynamic path handling to support changing the download folder. The app now verifies file existence and automatically re-downloads or updates paths if the archive location is moved.

## [0.7.8] - 2025-12-23

### Fixed
- **Shutdown UX**: Implemented graceful shutdown for both UI and CLI, silencing noisy tracebacks when stopping with `Ctrl+C`.

## [0.7.7] - 2025-12-23

### Fixed
- **UI Layout**: Fixed regression where content couldn't be scrolled in the new top-nav layout.
- **Sticky Navigation**: Ensured the top navigation bar remains solidly fixed at the top of the interface.

## [0.7.6] - 2025-12-23

### Changed
- **UI Layout**: Successfully refactored the dashboard to a top-nav structure, relocating the sidebar menu to the top and streamlining the header area.

## [0.7.5] - 2025-12-23

### Added
- **Sync Control**: Added a "STOP" button to the UI to cancel ongoing synchronization tasks immediately.
- **Custom Port**: New `--port` CLI argument to specify a custom port for the web dashboard.
- **Smart Defaults**: Defaults sync to "today" if no filter is provided, preventing accidental overloads.

## [0.7.4] - 2025-12-23

### Added
- **UI-Driven Onboarding**: New dashboard experience for first-time users to set up providers.
- **Browser-Based Authentication**: Support for OAuth (Gmail) and Device Flow (M365) directly in the UI.
- **Secret Management**: Upload and manage `credentials.json` or MSAL configs via the dashboard.

### Fixed
- **Robust Path Handling**: Fixed crashes when running via `uvx` in directories without existing configuration.

## [0.7.3] - 2025-12-23

### Changed
- **Dependencies**: Removed internal `ImportError` guards for UI components; they are now strictly mandatory core dependencies. This ensures that tools like `uvx` always include the necessary dashboard requirements.

## [0.7.2] - 2025-12-23

### Changed
- **Dependencies**: Consolidated UI dependencies into the core package to ensure they are automatically resolved (e.g., when using `uvx`).

## [0.7.1] - 2025-12-23

### Changed
- **UI Polish**: Updated dashboard and CLI help to reflect v0.7.x capabilities.
- **Developer Experience**: Improved UI dependency error message to provide `uv`-specific sync commands.

## [0.7.0] - 2025-12-23

### Added
- **SQLite-Powered Persistence**: Replaced text-based metadata with a robust local SQLite database.
  - Instant message tracking and skip logic using indexed `message_id`.
  - Faster Web UI stats and history via optimized SQL queries.
- **Local-First Sync Architecture**:
  - **Auto-Indexing**: New logic automatically maps local files to the database, skipping downloads for found-on-disk content.
  - **Local-Only Mode**: Added `--local-only` flag to index your archive without reaching out to email providers.
- **Consolidated Checkpoints**: Sync checkpoints are now securely stored in SQLite, with automatic one-time migration from `checkpoint.json`.

### Fixed
- Improved reliability of the download loop when processing large batches.
- Fixed potential data corruption when sync is interrupted.

## [0.6.0] - 2025-12-23

### Added
- **Optional Web UI Dashboard**: A high-end, visual interface for managing your archive.
  - New `--ui` flag to launch the dashboard instantly.
  - **Premium Design**: Built with React and Tailwind CSS, featuring a glassmorphism dark mode.
  - **Intelligence Hub**: Real-time stats on classification, extraction, and sync progress.
  - **Metadata Browser**: Explore and filter your archived emails with AI summaries and categories.
  - **Easy Setup**: Zero-configuration launch via FastAPI.

### Changed
- Refactored project structure to support optional web server logic.
- Updated `pyproject.toml` with `ui` optional dependency group.

## [0.5.0] - 2025-12-23

### Added
- **Advanced Metadata Extraction**: Automatically extract structured data from email bodies.
  - New `--extract` flag to enable deep processing.
  - Extracts summaries, action items, organizations, people, and monetary values.
  - **Smart Schema**: Automatically identifies email types (invoice, meeting, etc.) and extracts relevant fields.
  - Shared LLM infrastructure with classification for efficiency.
- **Recipient Metadata**: Added full support for `To`, `Cc`, and `Bcc` headers in both metadata storage and AI context.
- **New Extractor Module**: `email_archiver/core/extractor.py`.

### Changed
- Refactored `main.py` to support multi-stage AI processing (Classification -> Extraction).
- Enhanced metadata schema to include recipient info and extraction blocks.

## [0.4.0] - 2025-12-23

### Added
- **Local LLM Support**: Support for local LLM providers via OpenAI-compatible APIs.
  - Integration with **Ollama**, **LM Studio**, and **llama.cpp**.
  - New CLI arguments: `--llm-provider` and `--llm-base-url`.
  - Automatic detection of default local endpoints.
  - No API key required for local providers.

## [0.3.0] - 2025-12-23

### Added
- **AI-Powered Email Classification**: Classify emails using OpenAI's GPT models.
  - Skip promotional/social emails automatically.
  - Save classification metadata to JSONL.

## [0.2.0] - 2025-12-23

### Added
- **Webhook Integration**: Send downloaded emails to processing endpoints.
- **Custom Download Directory**: `--download-dir` support.
- **UVX Support**: Reorganized for zero-install usage via `uvx email-archiver`.

## [0.1.0] - 2025-12-23

### Added
- Initial release.
- Gmail and Microsoft 365 support.
- OAuth2 authentication.
- Incremental checkpointing.
