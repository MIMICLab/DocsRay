# Changelog

All notable changes to this project will be documented in this file.

## [1.9.0] - 2025-02-01

### Added
- **LibreOffice Integration**: Enhanced document conversion capabilities
  - Automatic detection and use of LibreOffice when available
  - Improved conversion quality for Office documents (DOCX, XLSX, PPTX)
  - Better support for OpenDocument formats (ODT, ODS, ODP)
  - Enhanced HWP/HWPX document handling with LibreOffice
  - Fallback mechanisms when LibreOffice is not available

### Changed
- File converter now prioritizes LibreOffice for office document conversions
- Improved error messages and conversion feedback
- Better handling of conversion failures with automatic fallback methods

## [1.8.0] - 2025-01-31

### Added
- **Video Input Support**: Process and extract information from video files
  - Automatic audio extraction from video formats
  - Frame extraction for visual content analysis
  - Support for common video formats (MP4, AVI, MOV, etc.)
- **Audio Input Support**: Direct processing of audio files
  - Transcription using faster-whisper for speech-to-text
  - Support for various audio formats (MP3, WAV, M4A, etc.)
- **Multimedia Processing Pipeline**: New `multimedia_processor.py` module
  - Unified interface for handling video and audio inputs
  - Automatic format detection and conversion
  - Integration with existing document processing pipeline

### Changed
- Enhanced file converter to support multimedia file types
- Updated dependencies to include faster-whisper for audio transcription

## [1.7.2] - 2025-01-26

### Added
- Configurable `--timeout` parameter for `perf-test` command
  - Allows custom request timeout in seconds
  - No timeout if parameter is not specified (replaces hardcoded 300 seconds)

### Changed
- Modified `perf-test` command to accept optional timeout parameter
- Updated error messages to show actual timeout value instead of hardcoded 300 seconds

## [1.7.1] - 2025-01-25

### Added
- Auto-restart functionality for Web, API, and MCP servers with `--auto-restart` flag
- Request timeout monitoring for API server (triggers restart on timeout when auto-restart is enabled)
- Optional `--max-retries` parameter (unlimited retries if not specified)
- Configurable `--retry-delay` parameter for restart attempts

### Changed
- `--timeout` parameter is now optional for both web and API (no timeout if not specified)
- `--pages` parameter is now optional for web interface (process all pages if not specified)
- Updated FastAPI from deprecated `@app.on_event` to modern lifespan context manager
- API server now tracks request processing activity via `/activity` endpoint

### Fixed
- Fixed deprecation warning in FastAPI shutdown event handler
- Improved process cleanup in auto-restart monitor
- Better handling of zombie processes when restarting services

## [1.7.0] - 2025-01-24

### Changed
- **BREAKING CHANGE**: Modified embedding synthesis method from element-wise addition to concatenation
  - This change doubles the embedding dimension by concatenating two model outputs instead of adding them
  - Results in better semantic representation but requires reindexing of existing documents

### Technical Details
- Changed `np.add(emb_1, emb_2)` to `np.concatenate([emb_1, emb_2])` in `get_embedding` method
- Updated batch processing in `get_embeddings` to use list comprehension with concatenation
- Both embeddings are now L2-normalized after concatenation

### Removed
- Removed `mteb_embedding.py` test file

## [1.6.2] - Previous Release

- Previous release details...