# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
