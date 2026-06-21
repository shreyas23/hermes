<img width="1097" height="768" alt="hermes" src="https://github.com/user-attachments/assets/2d3c9f9d-8914-4739-8481-a4db8d68504a" />

# Hermes

Local macOS app that converts documents, articles, and feeds into audio. Runs entirely on-device — no accounts, no cloud, no subscriptions.

**Supports:** PDF, DOCX, Markdown, HTML, RTF, plain text, web URLs

## Quick start

Requires macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/shreyas23/hermes.git
cd hermes
uv run python app.py
```

## Features

- Sentence-synced teleprompter view with click-to-jump
- Cached WAV audio with native seeking (no streaming buffer)
- 0.5x–2x playback speed
- Auto-resuming progress, saves every 30s
- Library with auto-categorization, collections, sidebar navigation
- PDF structure extraction: TOC, headings, chapter navigation
- SSE-based real-time generation progress

## Controls

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `Left` / `Right` | Previous / next sentence |
| `-15` / `+15` | Skip 15 seconds |
| `Escape` | Stop |

## Import methods

| Method | Input |
|--------|-------|
| URL | Article URL — text extracted via trafilatura |
| File | Local file path |
| Folder | Batch import all supported files |
| Text | Raw text with title |

Audio generates in background at ~4x realtime.

## Roadmap

**1. Core loop:** play queue with auto-advance, global media keys, sleep timer

**2. Import friction:** drag-and-drop, watch folders

**3. Comprehension:** transcript search, bookmarks, annotations, highlight export

**4. Audio quality:** Edge TTS / OpenAI TTS voices

**5. Content expansion:** RSS subscriptions, news aggregation, daily briefing

**6. Polish & export:** mini player, inline images, better PDF tables, auto-tagging, filtered collections, speed-specific caching, MP3 export

---

## Development

```bash
git clone https://github.com/shreyas23/hermes.git && cd hermes && uv sync
uv run python app.py
```

Flask on `:5123`, PyWebView opens a native WebKit window. Hit `127.0.0.1:5123` in a browser for debugging.

### Architecture

```
PyWebView (WebKit)
├── Sidebar (library, nav, collections)
├── Teleprompter (sentence-synced scrolling)
└── Controls (scrubber, speed, skip)

Flask (port 5123)
├── /api/library, /api/import
├── SSE for generation progress
├── extractors.py — PDF/DOCX/HTML/MD/RTF/TXT
├── audio.py — say → WAV → concat → cache
└── models.py — SQLite (library.db)
```

### Audio pipeline

1. Sentence split via [pysbd](https://github.com/nipunsadvilkar/pysbd)
2. Per-sentence WAV via macOS `say -o`
3. Concatenate into `master.wav`
4. Record sentence→timestamp mapping for teleprompter sync
5. Cache — subsequent plays are instant with native seeking

### Data

```
~/hermes-library/
├── library.db          # SQLite: metadata, text, timelines, progress
└── audio/<item_id>/
    └── master.wav      # 22050Hz mono 16-bit PCM (~150MB/hr)
```

Original files are not copied. Only extracted text is stored.

### Dependencies

[uv](https://docs.astral.sh/uv/) managed. Key packages: flask, pywebview, pymupdf, python-docx, beautifulsoup4, striprtf, pysbd, trafilatura.

### Extending

**New format:** Add extension to `SUPPORTED_EXTENSIONS` in `extractors.py`, implement `_extract_<format>()`, add to dispatch table.

**New TTS engine:** Replace `subprocess.run(['say', ...])` in `audio.py`. Contract: produce WAV at given path for given text. Concat, cache, and timeline work unchanged.

## Contributing

Fork, branch, test with real documents, open a PR. Vanilla JS frontend, no build step.

## License

MIT
