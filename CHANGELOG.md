# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
