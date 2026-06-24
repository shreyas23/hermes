<img width="1097" height="768" alt="hermes" src="https://github.com/user-attachments/assets/2d3c9f9d-8914-4739-8481-a4db8d68504a" />

# Hermes

Local macOS app that converts documents, articles, and feeds into audio. Runs entirely on-device — no accounts, no cloud, no subscriptions.

**Supports:** PDF, DOCX, Markdown, HTML, RTF, plain text, web URLs, RSS/Atom feeds

## Quick start

Requires macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/shreyas23/hermes.git
cd hermes
uv run python app.py
```

## Features

- **Teleprompter** — sentence-synced scrolling with click-to-jump
- **Multiple TTS engines** — Edge TTS (online), macOS Say, Kokoro (local CPU), Kokoro MLX (local GPU), Piper (local, fast). Per-item engine selection via split button
- **Playback** — cached audio with native seeking, 0.5x–2x speed, auto-resuming progress
- **Play queue** — line up items for back-to-back playback, Play Next / Add to Queue via right-click
- **Sleep timer** — auto-pause after a set duration or at end of current item
- **Global media keys** — play/pause/skip from anywhere via Media Session API
- **Discover** — search Wikipedia, subscribe to RSS/Atom feeds and Substack newsletters
- **Import** — URL, file, folder scan, drag-and-drop, watch folders (auto-import), pasted text
- **Reading tools** — transcript search, bookmarks & annotations
- **Library** — collections, source-type filtering, search, structured PDF navigation (TOC, chapters)
- **Design system** — three visual themes (Ink, Glass, Aurora) with light/dark modes
- **Privacy** — fully local, all data in `~/hermes-library/`, nothing leaves the machine

## Controls

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `Left` / `Right` | Previous / next sentence |
| `-15` / `+15` | Skip 15 seconds |
| `Escape` | Stop |

## TTS Engines

| Engine | Type | Quality | Speed | Notes |
|--------|------|---------|-------|-------|
| Edge TTS | Online | High | Fast | Microsoft neural voices, requires internet |
| macOS Say | Local | Low | Fast | Built-in system voices |
| Kokoro | Local (CPU) | High | Moderate | 82M param model, 28 English voices, auto-downloads ~120MB |
| Kokoro MLX | Local (GPU) | High | Fast | Apple Silicon GPU/ANE, same voices, ~2GB memory |
| Piper | Local (CPU) | Medium | Fast | Lightweight per-voice models (~30MB each), 22050Hz native |

Select the default engine in Settings. Override per-item via the dropdown on the Generate button.

---

## Development

```bash
git clone https://github.com/shreyas23/hermes.git && cd hermes
uv sync && npm install
uv run python app.py
```

Flask on `:5123`, PyWebView opens a native WebKit window.

### Architecture

```
PyWebView (WebKit)
├── Sidebar (library, nav, collections, search)
├── Teleprompter (sentence-synced scrolling, TOC panel)
├── Controls (scrubber, speed, skip, queue, sleep timer)
└── Settings (appearance, TTS, statistics, storage)

Flask (port 5123)
├── /api/library, /api/import, /api/settings, /api/stats
├── /api/voices — per-engine voice listing
├── SSE for generation progress
├── extractors.py — PDF/DOCX/HTML/MD/RTF/TXT
├── engines/ — TTS engine abstraction (edge, say, kokoro, kokoro-mlx, piper)
├── audio.py — orchestrator (ThreadPoolExecutor → concat → cache)
└── models.py — SQLite (library.db)
```

### Audio pipeline

1. Sentence split via [pysbd](https://github.com/nipunsadvilkar/pysbd)
2. Per-sentence WAV via the selected TTS engine
3. Concatenate into `master.wav`, convert to M4A
4. Record sentence→timestamp mapping for teleprompter sync
5. Cache — subsequent plays are instant with native seeking

### Data

```
~/hermes-library/
├── library.db           # SQLite: metadata, text, timelines, progress, settings
├── audio/<item_id>/
│   └── master.m4a       # Cached audio (M4A with WAV fallback)
└── models/              # Downloaded TTS model files (Kokoro, Piper)
```

Original files are not copied. Only extracted text is stored.

### Testing

```bash
uv run pytest              # Python unit + integration tests
npm run e2e:all            # Playwright E2E tests (runs on port 5199)
```

### Extending

**New format:** Add extension to `SUPPORTED_EXTENSIONS` in `extractors.py`, implement `_extract_<format>()`, add to dispatch table.

**New TTS engine:** Create `engines/<name>.py` with a `TTSEngine` subclass implementing `generate_sentence()` and `list_voices()`. Register in `engines/__init__.py`. Add voice setting to `models.DEFAULTS` and `_ALLOWED_SETTINGS` in `app.py`. Add UI option in `templates/index.html` and `static/js/settings.js`.

### Dependencies

Python: [uv](https://docs.astral.sh/uv/) managed. Key packages: flask, pywebview, pymupdf, python-docx, beautifulsoup4, striprtf, pysbd, trafilatura, kokoro-onnx, piper-tts.

Node: playwright (E2E tests only).

## Installing from DMG

Download `Hermes-<version>-mac.dmg` from the [latest release](https://github.com/shreyas23/hermes/releases). Open the DMG and drag Hermes to Applications.

On first launch, macOS will block the app because it isn't code-signed. To open it:

1. Right-click (or Control-click) `Hermes.app` → **Open**
2. Click **Open** in the dialog

Or from Terminal:

```bash
xattr -cr /Applications/Hermes.app
```

You only need to do this once.

## Building the DMG locally

Requires macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/shreyas23/hermes.git && cd hermes
uv sync
uv run pyinstaller hermes.spec --noconfirm
mkdir -p dist/dmg
cp -R dist/Hermes.app dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -volname "Hermes" -srcfolder dist/dmg -ov -format UDZO dist/Hermes.dmg
```

The DMG will be at `dist/Hermes.dmg`. Open it and drag Hermes to Applications. The same Gatekeeper bypass above applies to locally-built copies.

## Contributing

Fork, branch, test with real documents, open a PR. Vanilla JS frontend, no build step.

## License

MIT
