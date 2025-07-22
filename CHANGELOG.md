# Changelog

All notable changes to Chatterbox-TTS-Extended will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-01-22

### 🔧 Fixed
- **Silent crashes during Whisper model cleanup** - The program would crash unexpectedly when the Whisper model was being deleted from memory. Replaced with safer cleanup approach.
- **Tensor concatenation failures** - Inconsistent waveform shapes (mono vs stereo, different dimensions) caused `torch.cat()` to fail silently. Added automatic shape normalization.
- **Interface closing after processing** - The Gradio interface would close after completing a job, requiring restart for each new generation. Added persistent server configuration.
- **Auto-editor subprocess crashes** - The auto-editor `subprocess.run()` call could cause the entire program to exit if it returned a non-zero exit code. Added proper error handling.
- **Memory leaks during batch processing** - GPU memory wasn't properly cleared between file processing, causing VRAM exhaustion. Added comprehensive memory management.
- **Subprocess exit code propagation** - Some subprocess calls could propagate exit codes and terminate the main program unexpectedly.

### ✨ Added
- **Markdown file support** - Automatic conversion of `.md` files to plain text for TTS processing
- **Enhanced multi-file batch processing** - Individual file errors no longer stop the entire batch
- **Comprehensive debug output** - Detailed logging showing waveform shapes, processing steps, and error diagnostics
- **Automatic memory management** - GPU cache clearing and garbage collection between file processing
- **Persistent web interface** - Server stays open after processing completion for multiple generations
- **Server auto-restart capability** - Automatic recovery from server errors with fallback port selection
- **Crash prevention system** - Try-catch blocks throughout the pipeline with graceful error recovery
- **Enhanced file naming** - Clean filename generation with better special character handling
- **Memory usage monitoring** - Warnings and safeguards for GPU memory usage
- **Status indicators** - Clear feedback showing when the interface is ready for next generation

### ⚡ Improved
- **Whisper validation threshold** - Lowered from 0.95 to 0.90 for better handling of legal/technical text containing terms like "movant," "demurrer," etc.
- **Error recovery throughout TTS pipeline** - Graceful handling of failed chunks without stopping entire generation
- **Waveform loading robustness** - Automatic shape normalization and error handling for all audio loading operations
- **Multi-file processing reliability** - Each file processed independently with individual error handling
- **User feedback and messaging** - Better status messages, completion indicators, and error guidance
- **Debug information quality** - More detailed logging with specific error context and troubleshooting hints
- **Cross-platform compatibility** - Better filename handling for Windows/Linux/macOS
- **Memory efficiency** - Automatic cleanup and monitoring to prevent resource exhaustion

### 🏗️ Internal Changes
- **Enhanced error handling patterns** - Consistent try-catch blocks with specific error types
- **Improved subprocess management** - Safe handling of external process calls
- **Better resource cleanup** - Automatic memory and GPU cache management
- **Modular error recovery** - Isolated error handling that doesn't cascade failures
- **Enhanced logging system** - Structured debug output with color coding and context

## [1.0.0] - 2024-XX-XX

### Initial Release
- Full TTS pipeline with Whisper validation
- Multi-file processing capabilities
- Voice conversion functionality  
- Comprehensive audio post-processing
- Parallel processing support
- Auto-Editor integration
- FFmpeg normalization
- Multiple export formats (WAV/MP3/FLAC)
- Persistent settings system
- Complete Gradio web interface

---

## Migration Guide

### Upgrading from v1.0 to v2.0

**No breaking changes** - All existing functionality remains the same. The improvements are backwards compatible.

**New Benefits:**
- Your interface will now stay open after processing
- Better error messages if something goes wrong
- More reliable batch processing for multiple files
- Improved handling of legal/technical documents
- Better memory management for longer sessions

**Configuration Changes:**
- Whisper validation threshold automatically lowered to 0.90 (previously 0.95)
- Server now uses auto-restart and persistent connection by default
- Enhanced debug output is enabled by default

**File Changes:**
- New `.gitignore` file added for better repository management
- Improved README with detailed changelog and troubleshooting
- No changes to existing settings files or output formats 