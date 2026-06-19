# Hermes

Text-to-podcast desktop app for macOS. Converts documents and articles into audio with a teleprompter UI, library management, and podcast-style playback controls.

## Architecture

- **Backend:** Python + Flask (port 5123)
- **Window:** PyWebView (native macOS WebKit, not Electron)
- **TTS:** macOS `say -o` generates per-sentence WAV files, concatenated into a cached master WAV per item
- **Storage:** SQLite at `~/hermes-library/library.db`, audio cache at `~/hermes-library/audio/<item_id>/master.wav`
- **Sentence splitting:** pysbd
- **Frontend:** Vanilla HTML/CSS/JS, SSE for real-time updates

## Key files

- `app.py` — Flask routes + PyWebView entry point
- `models.py` — SQLite schema and queries (items, progress, collections)
- `audio.py` — TTS generation, WAV concatenation, caching
- `extractors.py` — Text extraction (PDF via pymupdf, DOCX via python-docx, HTML via bs4, RTF via striprtf, MD/TXT built-in)
- `static/app.js` — Frontend: library UI, teleprompter, audio playback, controls
- `static/style.css` — Dark theme styling
- `templates/index.html` — Main HTML layout

## Storage layout

All user data lives under `~/hermes-library/`:

```
~/hermes-library/
  library.db                # SQLite database (items, progress, collections)
  audio/
    <item_id>/
      master.wav            # Concatenated audio (22050Hz mono 16-bit PCM)
```

- **library.db** — contains item metadata (title, source_type, source_url, original_path), extracted text content, sentence arrays (JSON), timeline mappings (JSON), playback progress, and collection membership.
- **audio/<item_id>/master.wav** — cached TTS audio for each item. Generated once on import, ~150MB per hour of content. During generation, temporary per-sentence WAVs (`sent_0000.wav`, etc.) are created in the same directory and deleted after concatenation.
- Original files are NOT copied into the library — only extracted text is stored in the database.

## Running

```
cd ~/hermes && uv run python app.py
```

## Import flow

1. User imports via URL, file path, folder scan, or pasted text
2. Text extracted → split into sentences → stored in SQLite
3. Background thread generates per-sentence WAVs via `say -o`, concatenates into master.wav
4. SSE broadcasts generation progress to frontend
5. Once complete, audio is cached — subsequent plays are instant with native scrubbing

## Playback

- Single cached WAV file per item — HTML5 Audio with native seeking
- Teleprompter syncs via sentence→timestamp mapping stored in the timeline
- Speed control via `audio.playbackRate` (0.5x–2x)
- Progress saved every 30s, on pause, on stop, on item switch, on window close

## Dependencies

Managed via `uv`. Key deps: flask, pywebview, pymupdf, python-docx, beautifulsoup4, striprtf, pysbd, trafilatura.

Note: system pip/pip3 have a broken expat library on this machine — always use `uv` for dependency management.

## Future development

- **Inline images in transcript** — display images from articles/PDFs/DOCX in the teleprompter view, positioned between sentences where they appeared in the original. Caption/alt-text reading as a follow-on.
- **Play queue** — line up multiple items to play back-to-back, "Play Next" via right-click
- **Sleep timer** — auto-pause after N minutes
- **Search within transcript** — find text in the current item's teleprompter view
- **RSS feed subscriptions** — subscribe to feeds, auto-import new articles
- **Alternative TTS engines** — Edge TTS or OpenAI TTS for higher-quality voices
- **Speed-specific audio caching** — pre-generate audio at different speeds (currently speed is applied via playbackRate which changes pitch slightly)
- **Drag-and-drop import** — drop files onto the window to import
- **Export as podcast MP3** — export library items as MP3 files with metadata
