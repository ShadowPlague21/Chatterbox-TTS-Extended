# 🚀 Chatterbox-TTS-Extended — All Features & Technical Explanations

Chatterbox-TTS-Extended is a *power-user TTS pipeline* for advanced single and batch speech synthesis, voice conversion, and artifact-free audio generation. It is based on [Chatterbox-TTS](https://github.com/resemble-ai/chatterbox), but adds:

- **Multi-file input & batch output**
- **Custom candidate generation & validation**
- **Rich audio post-processing**
- **Whisper/faster-whisper validation**
- **Voice conversion (VC) tab**
- **Full-featured persistent UI with parallelism and artifact reduction**
- **🆕 Enhanced stability and crash prevention**
- **🆕 Improved multi-file processing with better error handling**
- **🆕 Markdown file support with automatic conversion**
- **🆕 Persistent interface that stays open after processing**

---

## 🆕 Recent Improvements (v2.0)

### **Enhanced Stability & Crash Prevention**
- **Fixed silent crashes** during Whisper model cleanup that previously caused the program to exit unexpectedly
- **Robust waveform loading** with automatic shape normalization to prevent tensor concatenation failures
- **Comprehensive error handling** throughout the TTS pipeline with graceful recovery
- **Memory management improvements** with automatic GPU cache clearing between file processing

### **Improved Multi-File Processing**
- **Better batch processing** with individual file error handling - one failed file won't stop the entire batch
- **Enhanced debug output** showing detailed progress, waveform shapes, and processing status
- **Automatic memory cleanup** between files to prevent VRAM exhaustion during large batches

### **Interface Stability**
- **Persistent interface** - the Gradio web interface now stays open after processing completion
- **Auto-restart mechanism** if the server encounters issues
- **Better user feedback** with clear status messages and completion indicators
- **Improved subprocess handling** for auto-editor to prevent program exit

### **Text Processing Enhancements**
- **Markdown support** - automatic conversion of .md files to plain text
- **Lowered Whisper validation threshold** from 0.95 to 0.90 for better handling of legal/technical text
- **Enhanced file naming** with clean filename generation for better organization

### **Quality of Life Improvements**
- **Better error messages** with specific guidance for troubleshooting
- **Status indicators** showing when the interface is ready for the next generation
- **Comprehensive logging** for easier debugging and issue resolution
- **Improved file handling** with better support for special characters in filenames

---

## 📋 Table of Contents

- [Recent Improvements](#-recent-improvements-v20)
- [Feature Summary Table](#feature-summary-table)
- [Text Input & File Handling](#text-input--file-handling)
- [Reference Audio](#reference-audio)
- [Voice/Emotion/Synthesis Controls](#voiceemotionsynthesis-controls)
- [Batching, Chunking & Grouping](#batching-chunking--grouping)
- [Text Preprocessing](#text-preprocessing)
- [Audio Post-Processing](#audio-post-processing)
- [Export & Output Options](#export--output-options)
- [Generation Logic & Quality Control](#generation-logic--quality-control)
- [Whisper Sync & Validation](#whisper-sync--validation)
- [Parallel Processing & Performance](#parallel-processing--performance)
- [Persistent Settings & UI](#persistent-settings--ui)
- [🎙️ Voice Conversion (VC) Tab](#️-voice-conversion-vc-tab)
- [Tips & Troubleshooting](#tips--troubleshooting)
- [Installation](#-installation)
- [Changelog](#-changelog)
- [Feedback & Contributions](#-feedback--contributions)

---

## Feature Summary Table

| Feature                                   | UI Exposed?   | Script Logic | Status |
| ----------------------------------------- | ------------- | ------------ | ------ |
| Text input (box + multi-file upload)      | ✔             | Yes          | ✅ Stable |
| Markdown file support (.md)              | ✔             | Yes          | 🆕 New |
| Reference audio (conditioning)            | ✔             | Yes          | ✅ Stable |
| Separate/merge file output                | ✔             | Yes          | ✅ Enhanced |
| Emotion, CFG, temperature, seed           | ✔             | Yes          | ✅ Stable |
| Batch/smart-append/split (sentences)      | ✔             | Yes          | ✅ Stable |
| Sound word remove/replace                 | ✔             | Yes          | ✅ Stable |
| Inline reference number removal           | ✔             | Yes          | ✅ Stable |
| Dot-letter ("J.R.R.") correction          | ✔             | Yes          | ✅ Stable |
| Lowercase & whitespace normalization      | ✔             | Yes          | ✅ Stable |
| Auto-Editor post-processing               | ✔             | Yes          | ✅ Enhanced |
| FFmpeg normalization (EBU/peak)           | ✔             | Yes          | ✅ Stable |
| WAV/MP3/FLAC export                       | ✔             | Yes          | ✅ Stable |
| Candidates per chunk, retries, fallback   | ✔             | Yes          | ✅ Enhanced |
| Parallelism (workers)                     | ✔             | Yes          | ✅ Enhanced |
| Whisper/faster-whisper backend            | ✔             | Yes          | ✅ Enhanced |
| Persistent settings (JSON/CSV per output) | ✔             | Yes          | ✅ Stable |
| Settings load/save in UI                  | ✔             | Yes          | ✅ Stable |
| Audio preview & download                  | ✔             | Yes          | ✅ Stable |
| Help/Instructions                         | ✔ (Accordion) | Yes          | ✅ Stable |
| Voice Conversion (VC tab)                 | ✔             | Yes          | ✅ Stable |
| Crash prevention & error recovery         | ✔             | Yes          | 🆕 New |
| Persistent interface (stays open)         | ✔             | Yes          | 🆕 New |

---

## Text Input & File Handling

- **Text box:** For direct text entry (single or multi-line).
- **Multi-file upload:** Drag-and-drop any number of `.txt` or `.md` files.
  - **🆕 Markdown support:** Automatically converts .md files to plain text
  - Choose to merge them into one audio or process each as a separate output file.
  - Outputs are named for sorting and reproducibility.
  - **🆕 Enhanced error handling:** Individual file failures won't stop batch processing
- **Reference audio input:** Upload or record a sample to condition the generated voice.
- **Settings file support:** Load or save all UI settings as JSON for easy workflow repeatability.

---

## Reference Audio

- **Voice Prompt (Conditioning):**
  - Upload or record an audio reference.
  - The TTS engine mimics the style, timbre, or emotion from the provided sample.
  - Handles missing/invalid reference audio gracefully.

---

## Voice/Emotion/Synthesis Controls

- **Emotion exaggeration:** Slider (0 = flat/neutral, 1 = normal, 2 = exaggerated emotion).
- **CFG Weight/Pace:** Controls strictness and speech pacing. High = literal, monotone. Low = expressive, dynamic.
- **Temperature:** Controls voice randomness/variety.
- **Random seed:** 0 = new random each run. Any number = repeatable generations.

---

## Batching, Chunking & Grouping

- **Sentence batching:** Groups sentences up to 300 characters per chunk (adjustable in code).
- **Smart-append short sentences:** When batching is off, merges very short sentences for smooth prosody.
- **Recursive long sentence splitting:** Automatically splits long sentences at `; : - ,` or by character count.
- **Parallel chunk processing:** Multiple chunks are generated at once for speed (user control).
- **🆕 Enhanced memory management:** Automatic cleanup between chunks to prevent VRAM exhaustion

---

## Text Preprocessing

- **Lowercase conversion:** Makes all text lowercase (optional).
- **Whitespace normalization:** Strips extra spaces/newlines.
- **Dot-letter fix:** Converts `"J.R.R."` to `"J R R"` to improve initialisms and names.
- **Inline reference number removal:** Automatically removes numbers after sentence-ending punctuation (e.g., `.188` or `."3`).
- **Sound word removal/replacement:** Configurable box for unwanted noises or phrases, e.g. `um`, `ahh`, or custom mappings like `zzz=>sigh`.
  - Handles standalone words, possessives, quoted patterns, and dash/punctuation-only removals.

---

## Audio Post-Processing

- **Auto-Editor integration:**
  - Trims silences/stutters/artifacts after generation.
  - **Threshold** and **margin** are adjustable in UI.
  - **Option to keep original WAV** before cleanup.
  - **🆕 Enhanced subprocess handling:** Prevents program crashes from auto-editor errors
- **FFmpeg normalization:**
  - **EBU R128:** Target loudness, true peak, dynamic range.
  - **Peak:** Quick normalization to prevent clipping.
  - All normalization parameters are user-adjustable.

---

## Export & Output Options

- **Multiple audio formats:** WAV (uncompressed), MP3 (320k), FLAC (lossless). Any/all selectable in UI.
- **Output file naming:** Each output includes base name, timestamp, generation, and seed for tracking.
- **🆕 Clean filename generation:** Better handling of special characters for cross-platform compatibility
- **Batch export:** If "separate files" is checked, each text file gets its own processed output.

---

## Generation Logic & Quality Control

- **Number of generations:** Generate multiple different outputs at once ("takes").
- **Candidates per chunk:** For each chunk, generate multiple variants.
- **Max attempts per candidate:** If validation fails, retries up to N times for best result.
- **Whisper validation:** Uses speech-to-text to check each candidate and picks the closest transcript match (can bypass for speed).
- **🆕 Improved validation threshold:** Lowered from 0.95 to 0.90 for better handling of legal/technical text
- **Fallback strategies:** If all candidates fail, use the longest transcript or highest similarity score.
- **🆕 Enhanced error recovery:** Graceful handling of failed chunks without stopping entire generation

---

## Whisper Sync & Validation

- **Model choice:** Select between OpenAI Whisper and faster-whisper (SYSTRAN). Both have multiple model sizes (VRAM vs. speed tradeoff).
- **Whisper backend and size exposed in UI:** Shows VRAM estimates and auto-disables if not needed.
- **Per-chunk Whisper validation:** Each audio chunk is transcribed and compared to its intended text.
- **🆕 Improved legal text handling:** Better recognition of legal terminology like "movant," "demurrer," etc.
- **Fallbacks:** If all candidates fail, configurable selection of longest transcript or highest score.
- **Bypass option:** Skip Whisper entirely (faster, but riskier for artifacts).
- **🆕 Safe model cleanup:** Prevents crashes during Whisper model memory cleanup

---

## Parallel Processing & Performance

- **Full parallelism:** User-configurable worker count (default 4).
- **Worker control:** Set to 1 for low-memory or debugging, higher for speed.
- **🆕 Enhanced VRAM management:** Better GPU memory cleanup and monitoring
- **🆕 Memory safety checks:** Warns when running low on GPU memory
- **🆕 Automatic garbage collection:** Between file processing to prevent memory leaks

---

## Persistent Settings & UI

- **JSON settings:** UI choices are saved/restored automatically, with option to import/export.
- **Per-output settings:** Every output audio file also gets a `.settings.json` and `.settings.csv` with all relevant parameters (for reproducibility and workflow management).
- **Complete Gradio UI:** All options available as toggles, sliders, dropdowns, checkboxes, and file pickers.
- **🆕 Persistent interface:** The web interface stays open after processing for multiple generations
- **🆕 Auto-restart capability:** Server can recover from errors automatically
- **Audio preview/download:** Listen to or download any generated output from the UI.
- **Help/Instructions:** Accordion panel with detailed explanations of every feature and control.
- **🆕 Better user feedback:** Clear status messages and processing indicators

---

## 🎙️ Voice Conversion (VC) Tab

Convert any voice to sound like another!\
**The Voice Conversion tab lets you:**

- Upload or record the **input audio** (the voice to convert).
- Upload or record the **target/reference voice** (the voice to match).
- Click **Run Voice Conversion** — get a new audio file with the same words but the target voice!

**Technical highlights:**

- Handles long audio by splitting into overlapping chunks, recombining with crossfades for seamless transitions.
- Output matches model's sample rate and fidelity.
- Automatic chunking and processing—no manual intervention needed.
- Option to disable watermarking.

---

## Tips & Troubleshooting

- **Out of VRAM or slow?**
  - Lower parallel workers
  - Use a smaller/faster Whisper model
  - Reduce number of candidates
  - **🆕 Check the new memory warnings** for GPU usage guidance
- **Artifacts/Errors?**
  - Increase candidates/retries
  - Adjust auto-editor threshold/margin
  - Refine sound word replacements
  - **🆕 Check the enhanced debug output** for specific error information
- **Choppy audio?**
  - Increase auto-editor margin
  - Lower threshold
- **Interface closes unexpectedly?**
  - **🆕 This should no longer happen** with the new stability improvements
  - Check console output for specific error messages
- **Reproducibility**
  - Use a fixed random seed

---

## 📝 Installation

Requires Python 3.10.x and [FFMPEG](https://ffmpeg.org/download.html).

Clone the repo:

```bash
git clone https://github.com/your-username/Chatterbox-TTS-Extended
```

Install requirements:

```bash
pip install --force-reinstall -r requirements.txt
# If needed, try requirements.base.with.versions.txt or requirements_frozen.txt
```

Run:

```bash
python Chatter.py
```

If FFMPEG isn't in your PATH, put the executable in the same directory as your script.

**🆕 The interface will now stay open after processing, so you can generate multiple audio files without restarting!**

---

## 📝 Changelog

### v2.0 - Stability & Enhancement Release
- **🔧 FIXED:** Silent crashes during Whisper model cleanup
- **🔧 FIXED:** Tensor concatenation failures due to inconsistent waveform shapes
- **🔧 FIXED:** Interface closing after processing completion
- **🔧 FIXED:** Auto-editor subprocess causing program exit
- **✨ NEW:** Markdown file support with automatic conversion
- **✨ NEW:** Enhanced multi-file batch processing with individual error handling
- **✨ NEW:** Comprehensive debug output and error reporting
- **✨ NEW:** Automatic memory management and GPU cache clearing
- **✨ NEW:** Persistent web interface that stays open after processing
- **✨ NEW:** Server auto-restart capability for better reliability
- **⚡ IMPROVED:** Lowered Whisper validation threshold for better legal text handling
- **⚡ IMPROVED:** Enhanced error recovery throughout the TTS pipeline
- **⚡ IMPROVED:** Better filename generation and special character handling
- **⚡ IMPROVED:** Memory usage monitoring and warnings

### v1.0 - Initial Release
- Full TTS pipeline with Whisper validation
- Multi-file processing capabilities
- Voice conversion functionality
- Comprehensive audio post-processing
- Parallel processing support

---

## 📣 Feedback & Contributions

Open an issue or pull request for suggestions, bug reports, or improvements!

**Contributing Guidelines:**
- Please test your changes thoroughly before submitting
- Include detailed descriptions of any new features or fixes
- Update the README and changelog for significant changes
- Ensure backward compatibility where possible

