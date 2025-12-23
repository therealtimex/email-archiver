# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-12-23

### Added
- **Local LLM Support**: Support for local LLM providers via OpenAI-compatible APIs.
  - Integration with **Ollama**, **LM Studio**, and **llama.cpp**.
  - New CLI arguments: `--llm-provider` and `--llm-base-url`.
  - Automatic detection of default local endpoints.
  - No API key required for local providers (defaults to "not-needed").
- **Flexible AI Infrastructure**: Decoupled classification from OpenAI-only dependency.
- **Provider-specific Defaults**:
  - Ollama: `http://localhost:11434/v1`
  - LM Studio: `http://localhost:1234/v1`
  - Local/llama.cpp: `http://localhost:8000/v1`

### Changed
- Refactored `EmailClassifier` to support generic OpenAI-compatible clients.
- Updated documentation with local LLM setup guides and examples.

## [0.3.0] - 2025-12-23

### Added
- **AI-Powered Email Classification**: Classify emails using OpenAI's GPT models
  - `--classify` flag to enable classification
  - `--openai-api-key` argument for API key
  - `--skip-promotional` to automatically skip promotional emails
  - `--metadata-output` to specify JSONL metadata file
  - Configuration via `config/settings.yaml` classification section
- **Smart Filtering**: Skip emails based on AI classification (promotional, spam, etc.)
- **Metadata Export**: Save classification results to JSONL format
  - Includes category, confidence, reasoning, tags, and importance
  - Structured data for downstream processing
- **New Classifier Module**: `email_archiver/core/classifier.py`
  - Supports custom categories
  - Configurable skip categories
  - Extracts email body for better classification

### Changed
- Added `openai>=1.0.0` dependency
- Updated configuration schema with classification settings
- Enhanced download loop to support classification workflow

### Fixed
- Improved error handling for classification failures

## [0.2.0] - 2025-12-23

### Added
- **Webhook Integration**: Send downloaded `.eml` files to webhook endpoints
  - `--webhook-url` CLI argument for webhook URL
  - `--webhook-secret` CLI argument for authorization header
  - Configuration via `config/settings.yaml`
- **Custom Download Directory**: `--download-dir` argument to specify output folder
- **UVX Support**: Restructured package for `uvx email-archiver` command
  - No installation needed with `uvx`
  - Proper Python package structure (`email_archiver`)
  - Clean command-line interface: `email-archiver` instead of `uv run main.py`
- **Comprehensive Documentation**:
  - Complete API reference (`docs/API.md`)
  - 21+ practical examples (`docs/EXAMPLES.md`)
  - Quick start guide (`docs/QUICKSTART.md`)
  - Release guide for maintainers (`docs/RELEASE.md`)
- **GitHub Actions Workflows**:
  - CI workflow for testing on Python 3.9-3.12
  - Release workflow for automated PyPI publishing
- **Progress Logging**: Shows progress every 1000 messages during fetch

### Changed
- **BREAKING**: Package structure reorganized
  - Main module moved to `email_archiver/main.py`
  - Core modules under `email_archiver/core/`
  - Command changed from `uv run main.py` to `email-archiver`
- **Authentication**: Switched to manual console flow for better reliability
  - Fixes Safari/localhost connection issues
  - More robust across different environments

### Fixed
- OAuth2 state mismatch errors on macOS Safari
- Gmail API 403 errors with better error messages
- File naming sanitization for cross-platform compatibility

## [0.1.0] - 2025-12-23

### Added
- Initial release
- Gmail and Microsoft 365 support
- OAuth2 authentication
- Advanced filtering (date-based, incremental, custom queries)
- Incremental checkpointing
- `.eml` file export with RFC822 compliance
- Basic configuration via `config/settings.yaml`
- Command-line interface with `argparse`

[0.2.0]: https://github.com/therealtimex/email-archiver/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/therealtimex/email-archiver/releases/tag/v0.1.0
