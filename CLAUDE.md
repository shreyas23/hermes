# Hermes

Text-to-podcast desktop app for macOS. Converts documents and articles into audio with a teleprompter UI, library management, and podcast-style playback controls.

## Git conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `style:`, `docs:`, `chore:`)
- Keep commits small and isolated — one logical change per commit
- Author: `shreyas23 <shreyas.niradi@gmail.com>`

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
- `extractors.py` — Text extraction (PDF via pymupdf4llm, DOCX via python-docx, HTML via bs4, RTF via striprtf, MD/TXT built-in)
- `static/js/app.js` — Frontend: init, item opening, SSE events
- `static/js/reader-highlight.js` — Reader view rendering, sentence highlighting, TOC panel
- `static/js/player.js` — Audio playback, scrubber, progress saving
- `static/js/sidebar.js` — Library sidebar, item list, navigation
- `static/css/tokens.css` — Design tokens (colors, spacing, typography, glass tokens, accent glows)
- `static/css/layout.css` — App shell layout (sidebar, main area)
- `static/css/components.css` — Component styles (reader, controls, TOC, tables)
- `static/css/designs.css` — Design variant overrides (Aurora, Ink & Paper); Glass is the default in tokens.css
- `static/js/settings.js` — Settings modal logic, design/theme switching
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

- **library.db** — contains item metadata (title, source_type, source_url, original_path), extracted text content, sentence arrays (JSON), timeline mappings (JSON), playback progress, collection membership, reader_html (structured HTML for PDFs/articles), and toc (JSON table of contents for PDFs).
- **audio/<item_id>/master.wav** — cached TTS audio for each item. Generated once on import, ~150MB per hour of content. During generation, temporary per-sentence WAVs (`sent_0000.wav`, etc.) are created in the same directory and deleted after concatenation.
- Original files are NOT copied into the library — only extracted text is stored in the database.

## Running

```
cd ~/hermes && uv run python app.py
```

## Import flow

1. User imports via URL, file path, folder scan, or pasted text
2. Text extracted → split into sentences → stored in SQLite
3. **PDFs:** pymupdf4llm extracts structured markdown using `TocHeaders` for heading hierarchy from PDF bookmarks. Markdown is cleaned (TOC pages stripped, page footers removed, bold-only lines matching TOC entries promoted to headings), converted to HTML via the `markdown` library, and table rows/columns are merged to fix pymupdf4llm's cell-splitting artifacts. The result is stored as `reader_html` with a navigable `toc` (JSON array of `{level, title, id}` entries). Table rendering is controlled by the `pdf_tables` setting (default: `off`).
4. **URLs:** readability extracts article HTML, cleaned and stored as `reader_html`
5. Background thread generates per-sentence audio, concatenates into master file
6. SSE broadcasts generation progress to frontend
7. Once complete, audio is cached — subsequent plays are instant with native scrubbing

## Playback

- Single cached WAV file per item — HTML5 Audio with native seeking
- Teleprompter syncs via sentence→timestamp mapping stored in the timeline
- Speed control via `audio.playbackRate` (0.5x–2x)
- Progress saved every 30s, on pause, on stop, on item switch, on window close

## Dependencies

Managed via `uv`. Key deps: flask, pywebview, pymupdf, pymupdf4llm, markdown, python-docx, beautifulsoup4, striprtf, pysbd, trafilatura.

Note: system pip/pip3 have a broken expat library on this machine — always use `uv` for dependency management.

## Design system

The UI supports multiple visual designs, switchable via Settings > Design. The system is token-based — component CSS references design tokens (`--glass-bg`, `--accent-glow`, `--glass-blur`, etc.) and never contains design-specific values.

**Current designs:**
- `glass` (default) — frosted translucency, backdrop-blur, Apple blue accent
- `aurora` — lavender accent, warm-to-cool gradient body, tinted glass, rounder corners
- `ink` — monochromatic (accent = text color), opaque surfaces, no blur/glow, minimal shadows

**How it works:** Each design is a `[data-design="..."]` CSS selector block in `designs.css` that overrides tokens from `tokens.css`. Glass is the implicit default (its tokens live in `tokens.css` directly). Light/dark variants use `[data-design="..."][data-theme="dark"]` selectors. The `data-design` attribute is set on `<html>`, initialized from localStorage in the `<head>` script, and persisted to both localStorage and SQLite on change.

**Adding a new design:**
1. Add a token override block to `static/css/designs.css` (light + dark variants)
2. Add an `<option>` to the `#setting-design` select in `templates/index.html`
3. Key tokens to override: `--accent`, `--glass-bg`, `--glass-blur` (set to `blur(0px)` for opaque), `--glass-border`, `--glass-shadow`, `--accent-glow` (set to `none` to disable), `--radius-md`/`--radius-lg`, `--shadow-*`, plus body background and reading highlight via element selectors

## Settings

Stored in SQLite `settings` table. Key settings:
- `design` — `glass` (default), `aurora`, or `ink`
- `tts_engine` — `edge` (default) or `say`
- `edge_voice` / `say_voice` — voice selection per engine
- `pdf_tables` — `off` (default) disables HTML table rendering in PDFs; set to `on` to enable (tables are often broken by pymupdf4llm's cell-splitting)

## Future development

- **PDF table improvements** — pymupdf4llm splits multi-line PDF cells into extra rows/columns; current post-processing merges them but results are imperfect. `pdf_tables` setting defaults to `off` until quality improves.
- **Inline images in transcript** — display images from articles/PDFs/DOCX in the teleprompter view, positioned between sentences where they appeared in the original. Caption/alt-text reading as a follow-on.
- **Play queue** — line up multiple items to play back-to-back, "Play Next" via right-click
- **Sleep timer** — auto-pause after N minutes
- **Search within transcript** — find text in the current item's teleprompter view
- **RSS feed subscriptions** — subscribe to feeds, auto-import new articles
- **Alternative TTS engines** — Edge TTS or OpenAI TTS for higher-quality voices
- **Speed-specific audio caching** — pre-generate audio at different speeds (currently speed is applied via playbackRate which changes pitch slightly)
- **Drag-and-drop import** — drop files onto the window to import
- **Export as podcast MP3** — export library items as MP3 files with metadata
