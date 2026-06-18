# Sayfiles

Turn any document or article into a podcast. Sayfiles is a macOS desktop app that converts text into speech with a teleprompter-style reading view, a full library system, and podcast-grade playback controls.

Paste a URL, drop in a PDF, or import a folder of documents — Sayfiles extracts the text, generates audio using macOS text-to-speech, and gives you a native app experience with scrubbing, speed control, and progress tracking.

## Features

- **Multi-format support** — PDF, DOCX, Markdown, HTML, RTF, plain text
- **Article import** — paste any URL to extract and listen to web articles
- **Teleprompter view** — highlighted sentence tracking synced to audio playback
- **Native scrubbing** — cached audio with smooth, sample-accurate seeking
- **Speed control** — 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x playback
- **Library management** — organize content with auto-categorization and custom collections
- **Progress tracking** — resume exactly where you left off, auto-saves every 30 seconds
- **Mini player** — persistent playback bar while browsing your library
- **Keyboard shortcuts** — Space (play/pause), arrows (skip sentences), Escape (stop)
- **Offline** — all processing happens locally, no API keys or accounts needed

## Requirements

- **macOS** (uses native `say` TTS and WebKit via PyWebView)
- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and run
git clone https://github.com/shreyas23/sayfiles.git
cd sayfiles
uv run python app.py
```

A native window opens. Click **+** to import your first article or document.

## Usage

### Importing content

Click the **+** button in the top-right corner of the sidebar to open the import dialog:

| Method | Description |
|--------|-------------|
| **URL** | Paste an article URL — text is extracted automatically |
| **File** | Enter a path to a local file (PDF, DOCX, MD, TXT, HTML, RTF) |
| **Folder** | Scan a folder and import files individually |
| **Text** | Paste raw text with a title |

After importing, audio generation begins in the background. A progress bar shows the status — you can cancel at any time.

### Playback controls

| Control | Action |
|---------|--------|
| `Space` | Play / Pause |
| `Left Arrow` | Previous sentence |
| `Right Arrow` | Next sentence |
| `-15` / `+15` | Skip back / forward 15 seconds |
| Speed button | Cycle through playback speeds |
| Scrubber | Drag to seek to any position |
| `Escape` | Stop playback |

Click any sentence in the teleprompter to jump directly to it.

### Library

Content is auto-organized by source type (Articles, Documents, Text) and you can create custom collections. The sidebar shows:

- **Recent** — latest imports
- **In Progress** — items you've started listening to
- **Sources** — Articles, Documents, Text
- **Collections** — user-created groups

## Architecture

```
┌─────────────────────────────────────────────┐
│              PyWebView (WebKit)             │
│  ┌────────┐  ┌────────────────────────────┐ │
│  │Sidebar │  │     Teleprompter View      │ │
│  │Library │  │  sentence-synced scrolling  │ │
│  │Nav     │  │                            │ │
│  └────────┘  └────────────────────────────┘ │
│  ┌────────────────────────────────────────┐  │
│  │  Controls: ◀◀ ▶ ⏸ ▶▶ ──●──── 2:35    │  │
│  └────────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│                Flask (port 5123)             │
│  Routes: /api/library, /api/import, SSE     │
├─────────────────────────────────────────────┤
│  extractors.py │ audio.py    │ models.py    │
│  PDF/DOCX/HTML │ say → WAV   │ SQLite       │
│  MD/RTF/TXT    │ concat/cache│ library.db   │
└─────────────────────────────────────────────┘
```

### Key files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, SSE, PyWebView entry point |
| `models.py` | SQLite schema and queries (items, progress, collections) |
| `audio.py` | TTS generation, WAV concatenation, caching, cancellation |
| `extractors.py` | Text extraction per format (pymupdf, python-docx, bs4, striprtf) |
| `static/app.js` | Frontend: library UI, teleprompter, audio playlist, controls |
| `static/style.css` | Dark theme styling |
| `templates/index.html` | HTML layout |

### How audio generation works

1. Text is split into sentences using [pysbd](https://github.com/nipunsadvilkar/pysbd)
2. Each sentence is rendered to a WAV file via macOS `say -o`
3. Individual WAVs are concatenated into a single `master.wav` per item
4. Sentence timestamps are recorded for teleprompter sync
5. The master WAV is cached — subsequent plays load instantly with native seeking

Audio is generated at ~4x real-time (a 5-minute article takes ~75 seconds).

### Data storage

All user data lives in `~/sayfiles-library/`:

```
~/sayfiles-library/
├── library.db              # SQLite: metadata, text, timelines, progress
└── audio/
    └── <item_id>/
        └── master.wav      # Cached audio (22050Hz, mono, 16-bit PCM)
```

- **~150MB of disk per hour of audio content**
- Original files are not copied — only extracted text is stored
- Deleting an item removes its audio cache automatically

## Development

### Setup

```bash
git clone https://github.com/shreyas23/sayfiles.git
cd sayfiles
uv sync
```

### Running in development

```bash
uv run python app.py
```

The Flask server starts on `http://127.0.0.1:5123` and a PyWebView window opens pointing to it. You can also open `http://127.0.0.1:5123` in a browser for debugging.

### Project structure

```
sayfiles/
├── app.py              # Flask app + PyWebView launcher
├── audio.py            # TTS generation and audio caching
├── extractors.py       # Text extraction (PDF, DOCX, HTML, etc.)
├── models.py           # SQLite database layer
├── static/
│   ├── app.js          # Frontend application logic
│   └── style.css       # Styling
├── templates/
│   └── index.html      # HTML layout
├── pyproject.toml      # Dependencies and project config
├── uv.lock             # Locked dependency versions
├── CLAUDE.md           # Internal dev notes
└── README.md
```

### Dependencies

Managed with [uv](https://docs.astral.sh/uv/). All dependencies are declared in `pyproject.toml`:

| Package | Purpose |
|---------|---------|
| flask | HTTP backend and API |
| pywebview | Native macOS window (WebKit) |
| pymupdf | PDF text extraction |
| python-docx | DOCX text extraction |
| beautifulsoup4 | HTML text extraction |
| striprtf | RTF text extraction |
| pysbd | Sentence boundary detection |
| trafilatura | Web article extraction |

### Adding a new file format

1. Add the extension to `SUPPORTED_EXTENSIONS` in `extractors.py`
2. Write an `_extract_<format>(path: str) -> str` function
3. Add it to the dispatch table in `extract_text()`

### Adding a new TTS engine

The TTS layer is in `audio.py`. Replace the `subprocess.run(['say', ...])` call in `generate_audio_for_item()` with your engine. The contract: produce a WAV file at the given path for the given text. Everything downstream (concatenation, caching, timeline) works unchanged.

## Contributing

Contributions are welcome. Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test locally — run the app and verify your change works end-to-end
5. Commit with a clear message
6. Open a pull request

### Guidelines

- Keep dependencies minimal — this is a lightweight local app
- Frontend is vanilla JS — no build step, no framework
- Test with real documents (PDFs with complex layouts, long articles, edge cases)
- macOS-only features are fine — this app is inherently macOS-native

### Planned features

See the [Future development](CLAUDE.md#future-development) section in CLAUDE.md for the roadmap. Good first issues:

- **Sleep timer** — auto-pause after N minutes
- **Search within transcript** — find text in the teleprompter view
- **Drag-and-drop import** — drop files onto the window
- **Export as MP3** — export items with metadata

## License

MIT
