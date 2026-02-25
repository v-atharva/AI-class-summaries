# AI Class Summaries Pipeline (Zoom Recording Ingestion Stage)

This project is being built as a **multi-stage learning pipeline** for recorded classes:

1. Download Zoom recordings and transcripts
2. Generate high-quality, detailed summaries useful for study/revision
3. Enable grounded question answering in order to help students ask natural-language questions and find relevant answers with timestamps from the lecture.

The current repository is focused on **Stage 1: Zoom recording/transcript acquisition**.

---

## Current Stage

### Stage 1 (Implemented): Zoom Download + Transcript Capture

Given a Zoom recording URL, the CLI currently supports:

1. Manual login through real browser automation (SSO / 2FA friendly)
2. Recording metadata and media-link extraction
3. Download of selected assets:
   - video (`.mp4`)
   - transcript (`.vtt`)
   - converted transcript text (`.txt`, paragraph or timestamped format)

This stage provides the ingestion foundation for the next AI stages.

---

## Pipeline Roadmap

### Stage 2 (Planned): High-Quality Summary Generation

Goal: produce summaries that are dense, faithful, and useful for real course revision.

Planned outputs:
- Long-form structured summary (concepts, derivations, examples, caveats)
- Topic-wise sections and key takeaways
- Timestamp-linked notes per segment
- Possible “exam revision” and “quick recap” summary variants

### Stage 3 (Planned): Grounded QA over Course Content

Goal: answer user queries using transcript/summaries as source-of-truth and return relevant evidence.

Approach that I have on my mind:
- RAG over transcript chunks + summary chunks

---

## Required Packages

| Package | Purpose |
|---------|---------|
| `playwright` | Browser automation for authentication and extraction |
| `click` | CLI commands and interactive prompts |
| `requests` | Authenticated HTTP downloads |
| `rich` | Terminal UX, status output, and progress bars |

### Runtime Requirements

- Python `3.11+`
- Google Chrome installed (Playwright launches Chrome with `channel="chrome"`)

---

## Setup Instructions

### 1. Create Environment and Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Or:

```bash
make setup
```

### 2. Verify CLI

```bash
./zoom --help
```

### 3. Login Once

```bash
zoom login
```

Complete login in the opened browser and close the window to persist session state.

---

## Usage (Current Stage)

### Download with URL

```bash
zoom download "https://zoom.us/rec/share/..."
```

### Or prompt for URL

```bash
zoom download
```

The CLI then asks:
1. What to download (video/transcript/both)
2. Transcript format preferences
3. Output folder name

---

## Expected Output

Typical artifacts generated in your current working directory:

- `<recording_title>.mp4` (if video selected and available)
- `<recording_title>.vtt` (if transcript VTT selected)
- `<recording_title>.txt` (paragraph or timestamped transcript text)

---

## Processing Logic (Stage 1)

### 1. Session Management (`BrowserSessionManager`)

- Uses persistent Chrome profile under `.state/zoom/userdata`
- Saves storage snapshot to `.state/zoom/cookies.json`
- Restores cookies between runs to avoid repeated login

### 2. Media Extraction (`ZoomMediaScraper`)

- Navigates to recording URL in authenticated context
- Intercepts API/network responses to detect media URLs
- Falls back to DOM inspection (`video`, `track`) when needed
- Captures title/topic metadata for output naming

### 3. Download + Transcript Conversion

- `DownloadService.download_file(...)` streams files with progress
- `DownloadService.fetch_text(...)` fetches transcript text
- `TranscriptConverter` supports:
  - `vtt_to_paragraph(...)`
  - `vtt_to_timestamped_txt(...)`

---

## Local State

Session state is stored in:

```bash
.state/zoom/
```

Includes:
- `userdata/` (browser profile)
- `cookies.json` (cookie/storage snapshot)

This directory is local state and should not be committed.

---

## Development Commands

```bash
make lint
make format
make test
make run
make clean
```

---

## Project Structure

```text
root/
├── zoom                              # CLI launcher script
├── pyproject.toml                    # package metadata and dependencies
├── Makefile                          # development commands
├── README.md
├── Transcripts/                      # sample transcript outputs
└── zoom_downloader/
    ├── __init__.py
    ├── cli.py                        # CLI orchestration
    ├── browser.py                    # session persistence
    ├── scraper.py                    # recording URL extraction
    ├── downloader.py                 # authenticated downloads
    └── transcript.py                 # VTT parsing/conversion
```
