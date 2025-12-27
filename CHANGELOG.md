# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
