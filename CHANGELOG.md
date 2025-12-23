# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
